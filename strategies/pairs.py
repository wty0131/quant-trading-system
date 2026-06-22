"""
配对交易策略 — 统计套利

原理:
  1. 找两只高度相关的股票（如 招商银行 vs 兴业银行）
  2. 检验协整关系：价差(spread)长期均值回归
  3. 计算价差的 Z-Score
  4. Z > 2 → spread过宽 → 做空贵的，做多便宜的
  5. Z < 0 → spread回归 → 平仓

注意:
  - 配对交易的"一对"需要同时处理两只股票
  - 当前引擎以单symbol为主，本策略简化为价差模拟模式
  - 实现在 Notebook 中详细讲解

参数:
  lookback: 计算价差均/标准差的历史窗口
  entry_z:  入场 Z-score 阈值
  exit_z:   出场 Z-score 阈值
"""

import numpy as np
from collections import deque
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class PairsStrategy(Strategy):
    """
    配对交易（价差模式）

    实际使用时：
      - 先在 Notebook 中计算两只股票的价差序列
      - 将价差作为"虚拟品种"输入回测
      - 本策略在价差偏离时产生信号
    """

    def __init__(
        self,
        lookback: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.0,
    ):
        super().__init__()
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self._spreads: dict[str, deque[float]] = {}
        self._in_position = False
        self._position_direction = ""  # "long_spread" or "short_spread"

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        # 此时 bar.close = 当前价差（由 Notebook 预处理）
        self._update_price(bar.symbol, bar)

        if bar.symbol not in self._spreads:
            self._spreads[bar.symbol] = deque(maxlen=self.lookback + 10)
        self._spreads[bar.symbol].append(bar.close)

        spreads = list(self._spreads[bar.symbol])
        if len(spreads) < self.lookback:
            return None

        recent = spreads[-self.lookback:]
        mu = np.mean(recent)
        sigma = np.std(recent, ddof=1)
        if sigma < 1e-9:
            return None

        z_score = (bar.close - mu) / sigma

        # 入场逻辑
        if not self._in_position:
            if z_score > self.entry_z:
                # 价差过高 → 做空 spread（卖贵的买贱的）
                self._in_position = True
                self._position_direction = "short"
                return self._ask(bar)  # EXIT 信号表示反向操作
            elif z_score < -self.entry_z:
                # 价差过低 → 做多 spread（买贱的卖贵的）
                self._in_position = True
                self._position_direction = "long"
                return self._bid(bar)
        else:
            # 出场：Z 回到 0 附近
            if abs(z_score) < self.exit_z:
                self._in_position = False
                return self._ask(bar) if self._position_direction == "long" else self._bid(bar)

        return None
