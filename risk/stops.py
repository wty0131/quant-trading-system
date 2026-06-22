"""
止损/止盈系统 — 什么时候认错？

四种止损:
  FixedStop  — 固定止损: 亏损 > N% → 平仓
  ATRStop    — ATR止损:  从最高点回落 N×ATR → 平仓
  TrailingStop — 移动止损: 当前价 < N日最低 → 平仓
  TimeStop   — 时间止损: 持仓N天后仍不涨 → 平仓

StopManager — 管理多个止损，任一触发即平仓
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import numpy as np


class Stop(ABC):
    """止损抽象基类"""

    @abstractmethod
    def check(self, bar, entry_price: float, entry_time, **context) -> bool:
        """
        检查是否应该止损

        Args:
            bar:         当前 MarketEvent
            entry_price: 开仓价格
            entry_time:  开仓时间
            context:     额外信息 (ATR值等)

        Returns:
            True = 触发止损，应该平仓
        """
        ...


class FixedStop(Stop):
    """固定比例止损"""

    def __init__(self, loss_pct: float = 0.05):
        """
        Args:
            loss_pct: 最大亏损比例 (如 0.05 = 5%)
        """
        self.loss_pct = loss_pct

    def check(self, bar, entry_price: float, entry_time, **context) -> bool:
        loss = (bar.close - entry_price) / entry_price
        return loss < -self.loss_pct


class ATRStop(Stop):
    """ATR 动态止损 — 从开仓后最高价回落 N×ATR"""

    def __init__(self, atr_multiple: float = 2.0):
        """
        Args:
            atr_multiple: ATR 倍数 (如 2.0 = 2倍ATR)
        """
        self.atr_multiple = atr_multiple
        self._high_water_mark = 0.0

    def set_entry(self, entry_price: float):
        """设置/重置入场价"""
        self._high_water_mark = entry_price

    def check(self, bar, entry_price: float, entry_time, **context) -> bool:
        atr = context.get("atr", 0)
        if atr <= 0:
            return False
        self._high_water_mark = max(self._high_water_mark, bar.high)
        stop_price = self._high_water_mark - self.atr_multiple * atr
        return bar.close < stop_price


class TrailingStop(Stop):
    """移动止损 — 跌破 N 日最低"""

    def __init__(self, period: int = 10, price_history: list = None):
        """
        Args:
            period: 回看天数
            price_history: 最近 N 根 bar 的最低价序列（由 StopManager 注入）
        """
        self.period = period
        self._lows = []

    def feed(self, bar):
        """每根 bar 推送最低价"""
        self._lows.append(bar.low)
        if len(self._lows) > self.period * 2:
            self._lows = self._lows[-self.period * 2:]

    def check(self, bar, entry_price: float, entry_time, **context) -> bool:
        if len(self._lows) < self.period:
            return False
        recent_low = min(self._lows[-self.period:])
        return bar.close < recent_low


class TimeStop(Stop):
    """时间止损 — 持仓超时仍不涨 → 平仓"""

    def __init__(self, max_days: int = 20):
        self.max_days = max_days

    def check(self, bar, entry_price: float, entry_time, **context) -> bool:
        if entry_time is None:
            return False
        days_held = (bar.timestamp - entry_time).days
        # 同时要求不盈利（如果已经盈利，不触发时间止损）
        in_loss = bar.close < entry_price
        return days_held >= self.max_days and in_loss


class StopManager:
    """
    止损管理器 — 组合多个止损规则，任一触发即告警

    用法:
        stops = StopManager()
        stops.add(ATRStop(2.0))
        stops.add(TimeStop(20))

        # 开仓时通知
        stops.on_entry(entry_price, entry_time)

        # 每根 bar 调用
        if stops.check(bar, atr=0.025):
            print("止损触发！")
    """

    def __init__(self):
        self._stops: list[Stop] = []
        self._entry_price = 0.0
        self._entry_time = None

    def add(self, stop: Stop):
        self._stops.append(stop)

    def on_entry(self, entry_price: float, entry_time):
        """开仓时通知所有止损"""
        self._entry_price = entry_price
        self._entry_time = entry_time
        for s in self._stops:
            if isinstance(s, ATRStop):
                s.set_entry(entry_price)

    def check(self, bar, **context) -> bool:
        """任一止损触发返回 True"""
        for s in self._stops:
            if isinstance(s, TrailingStop):
                s.feed(bar)
            if s.check(bar, self._entry_price, self._entry_time, **context):
                return True
        return False
