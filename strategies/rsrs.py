"""
RSRS 阻力支撑相对强度

原理:
  每天的最高价(H)和最低价(L)做 OLS 线性回归:
    H = alpha + beta × L + epsilon

  beta 的标准化得分衡量买方相对于卖方的力量:
    - beta 大 → 买方推力强 → 看涨
    - beta 小 → 卖方打压 → 看跌

  用滚动窗口计算 RSRS 斜率，标准化后与阈值比较。

参数:
  window:  回归窗口（默认18日）
  buy_threshold: 买入阈值（RSRS标准化得分高于此值买入）
  sell_threshold: 卖出阈值（RSRS低于此值卖出）
"""

import numpy as np
from collections import deque
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class RSRSStrategy(Strategy):
    """RSRS 择时"""

    def __init__(
        self,
        window: int = 18,
        buy_threshold: float = 0.7,
        sell_threshold: float = -0.7,
    ):
        super().__init__()
        self.window = window
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self._in_position = False
        self._highs: dict[str, deque[float]] = {}
        self._lows: dict[str, deque[float]] = {}
        self._rsrs_history: dict[str, deque[float]] = {}

    def _ensure_symbol(self, symbol: str):
        for d in [self._highs, self._lows, self._rsrs_history]:
            if symbol not in d:
                d[symbol] = deque(maxlen=self.window + 50)

    def _calc_rsrs(self, symbol: str) -> float | None:
        """计算滚动窗口的 RSRS 标准化得分"""
        highs = list(self._highs[symbol])
        lows = list(self._lows[symbol])
        if len(highs) < self.window:
            return None

        # 滚动窗口计算 beta
        betas = []
        for i in range(self.window - 1, len(highs)):
            h_window = highs[i - self.window + 1 : i + 1]
            l_window = lows[i - self.window + 1 : i + 1]
            if len(h_window) < 2:
                continue
            # OLS: H = alpha + beta * L
            l_arr = np.array(l_window)
            h_arr = np.array(h_window)
            cov = np.cov(l_arr, h_arr)[0, 1]
            var = np.var(l_arr)
            if var > 0:
                betas.append(cov / var)

        if len(betas) < 2:
            return None

        # 标准化：z-score = (当前beta - 均值) / 标准差
        mu = np.mean(betas)
        sigma = np.std(betas, ddof=1)
        if sigma == 0:
            return 0.0
        return float((betas[-1] - mu) / sigma)

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        self._ensure_symbol(bar.symbol)

        self._highs[bar.symbol].append(bar.high)
        self._lows[bar.symbol].append(bar.low)

        rsrs = self._calc_rsrs(bar.symbol)
        if rsrs is None:
            return None

        self._rsrs_history[bar.symbol].append(rsrs)

        if not self._in_position and rsrs > self.buy_threshold:
            self._in_position = True
            return self._bid(bar)

        if self._in_position and rsrs < self.sell_threshold:
            self._in_position = False
            return self._ask(bar)

        return None
