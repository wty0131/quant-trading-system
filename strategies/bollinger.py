"""
布林带策略 — 均值回归

原理:
  布林带 = MA(N) ± K × std(N)
  统计学上价格约95%落在带内（K=2时）
  → 跌破下轨 = 超卖 → 买入（赌价格回归中轨）
  → 升破上轨+回到中轨 = 平仓

参数:
  period: 均线周期 (默认20)
  k:      标准差倍数 (默认2.0)
"""

from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class BollingerStrategy(Strategy):
    """布林带均值回归"""

    def __init__(self, period: int = 20, k: float = 2.0):
        super().__init__()
        self.period = period
        self.k = k
        self._in_position = False
        self._entry_price = 0.0

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)

        # 计算布林带
        mid = self.sma(bar.symbol, self.period)
        if mid is None:
            return None

        # 手动算标准差（基类没有 std 方法，用 prices 算）
        prices = list(self._price_history[bar.symbol])
        if len(prices) < self.period:
            return None
        recent = prices[-self.period:]
        import numpy as np
        std = float(np.std(recent, ddof=1))

        upper = mid + self.k * std
        lower = mid - self.k * std

        # 信号逻辑
        if not self._in_position:
            # 跌破下轨 → 买入
            if bar.close <= lower:
                self._in_position = True
                self._entry_price = bar.close
                return self._bid(bar)
        else:
            # 回到中轨以上 → 平仓
            if bar.close >= mid:
                self._in_position = False
                return self._ask(bar)

        return None
