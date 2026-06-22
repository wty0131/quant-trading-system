"""
海龟交易系统 — 完整趋势跟踪系统

理查德·丹尼斯 1983 年实验："交易可以像养海龟一样被教会"

四模块:
  入场: 价格突破 N 日最高价
  止损: 入场价 - 2×ATR（动态风控）
  加仓: 每涨 0.5×ATR 加一次，最多4次
  出场: 价格跌破 M 日最低价

关键认知:
  - 胜率极低(~35%)，盈亏比极高
  - 趋势跟踪在95%的时间亏小钱，5%的时间赚大钱
  - ATR止损 = 让市场决定你该亏多少，不是凭感觉设固定止损
"""

from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class TurtleStrategy(Strategy):
    """海龟交易系统"""

    def __init__(
        self,
        entry_period: int = 20,    # 入场：突破 N 日高点
        exit_period: int = 10,     # 出场：跌破 M 日低点
        atr_period: int = 20,      # ATR 计算周期
        atr_stop: float = 2.0,     # 止损倍数
        max_units: int = 4,        # 最大加仓次数
    ):
        super().__init__()
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_stop = atr_stop
        self.max_units = max_units
        self._in_position = False
        self._entry_price = 0.0
        self._units = 0
        self._last_add_price = 0.0
        self._stop_price = 0.0

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)

        # 需要足够数据
        if len(list(self._price_history[bar.symbol])) < max(self.entry_period, self.atr_period):
            return None

        atr = self.atr(bar.symbol, self.atr_period)
        if atr is None:
            return None

        # ── 入场：突破 N 日最高（用最高价判断）──
        if not self._in_position:
            entry_high = self.highest(bar.symbol, self.entry_period)
            if entry_high and bar.high > entry_high:
                self._in_position = True
                self._entry_price = bar.close
                self._last_add_price = bar.close
                self._stop_price = bar.close - self.atr_stop * atr
                self._units = 1
                return self._bid(bar)
        else:
            # ── 止损 ──
            if bar.close <= self._stop_price:
                self._in_position = False
                self._units = 0
                return self._ask(bar)

            # ── 加仓：每涨 0.5×ATR ──
            if self._units < self.max_units:
                add_level = self._last_add_price + 0.5 * atr
                if bar.close >= add_level:
                    self._last_add_price = bar.close
                    self._stop_price = bar.close - self.atr_stop * atr
                    self._units += 1
                    return self._bid(bar)

            # ── 出场：跌破 M 日最低 ──
            exit_low = self.lowest(bar.symbol, self.exit_period)
            if exit_low and bar.close < exit_low:
                self._in_position = False
                self._units = 0
                return self._ask(bar)

        return None
