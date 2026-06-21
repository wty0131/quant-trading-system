"""
投资组合管理 — 现金、持仓、净值曲线

职责：
  - 接收 SignalEvent → 生成 OrderEvent
  - 接收 FillEvent   → 更新持仓和现金
  - 记录每日净值

注意：
  - A股最小交易单位 100 股（一手）
  - T+1 制度暂不模拟（简化）
"""

from .event import SignalEvent, OrderEvent, FillEvent, Direction, OrderType


class Portfolio:
    """
    组合管理器

    Args:
        initial_cash:     初始资金（默认 100 万）
        position_percent: 每次开仓使用的资金比例（默认 100%）
        lot_size:         最小交易单位（A股=100）
    """

    def __init__(
        self,
        initial_cash: float = 1_000_000,
        position_percent: float = 1.0,
        lot_size: int = 100,
    ):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position_percent = position_percent
        self.lot_size = lot_size

        # 当前持仓 {symbol: quantity}
        self.positions: dict[str, int] = {}

        # 净值历史 [(timestamp, nav)]
        self.nav_history: list[tuple] = []

        # 当前价格（每日更新）
        self._current_prices: dict[str, float] = {}

    # ── 信号 → 订单 ──
    def generate_order(
        self, signal: SignalEvent, current_price: float
    ) -> OrderEvent | None:
        """根据信号生成订单"""
        direction = signal.direction

        if direction == Direction.LONG:
            # 计算可买入股数
            available = self.cash * self.position_percent
            raw_qty = int(available / (current_price * self.lot_size)) * self.lot_size
            if raw_qty <= 0:
                return None
            return OrderEvent(
                timestamp=signal.timestamp,
                symbol=signal.symbol,
                direction=direction,
                order_type=OrderType.MKT,
                quantity=raw_qty,
            )

        elif direction == Direction.EXIT:
            # 平仓：卖出全部持仓
            current_qty = self.positions.get(signal.symbol, 0)
            if current_qty <= 0:
                return None
            return OrderEvent(
                timestamp=signal.timestamp,
                symbol=signal.symbol,
                direction=direction,
                order_type=OrderType.MKT,
                quantity=current_qty,
            )

        return None

    # ── 成交 → 更新持仓 ──
    def update(self, fill: FillEvent):
        """处理成交回报，更新持仓和现金"""
        if fill.direction == Direction.LONG:
            # 买入：扣现金，加持仓
            cost = fill.quantity * fill.price + fill.commission
            self.cash -= cost
            self.positions[fill.symbol] = (
                self.positions.get(fill.symbol, 0) + fill.quantity
            )

        elif fill.direction == Direction.EXIT:
            # 卖出：加现金，清持仓
            revenue = fill.quantity * fill.price - fill.commission
            self.cash += revenue
            self.positions[fill.symbol] = max(
                0, self.positions.get(fill.symbol, 0) - fill.quantity
            )

    # ── 每日标记 ──
    def mark_to_market(self, timestamp, prices: dict[str, float]):
        """按市价计算净值并记录"""
        self._current_prices = prices
        position_value = sum(
            qty * prices.get(sym, 0) for sym, qty in self.positions.items()
        )
        nav = self.cash + position_value
        self.nav_history.append((timestamp, nav))

    def current_nav(self) -> float:
        """当前净值"""
        if not self.nav_history:
            return self.initial_cash
        return self.nav_history[-1][1]

    def current_value(self) -> float:
        """当前持仓市值"""
        return sum(
            qty * self._current_prices.get(sym, 0)
            for sym, qty in self.positions.items()
        )

    def total_return(self) -> float:
        """总收益率"""
        return (self.current_nav() / self.initial_cash) - 1
