"""
PaperBroker — 纸交易模拟成交

不用真实账户。用实时价格模拟:
  - 市价单: 按当前 bar.close × (1 ± slippage) 立即成交
  - 限价单: 价格达到限价时成交
  - 记录虚拟持仓和余额

这是回测和实盘之间的桥梁——价格用真实的，但成交是模拟的。
"""

from datetime import datetime, timedelta
import uuid
from .broker import Broker
from .oms import OrderStatus


class PaperBroker(Broker):
    """纸交易券商"""

    def __init__(
        self,
        initial_cash: float = 1_000_000,
        slippage: float = 0.001,
        commission_rate: float = 0.0003,
    ):
        super().__init__(initial_cash)
        self.cash = initial_cash
        self.slippage = slippage
        self.commission_rate = commission_rate
        self.positions: dict[str, dict] = {}  # {symbol: {qty, avg_cost}}
        self.orders: dict[str, dict] = {}
        self.trade_history: list[dict] = []

    # ── Broker 接口实现 ──

    def submit_order(
        self, symbol, direction, quantity, order_type="MKT", limit_price=None
    ) -> str:
        order_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        self.orders[order_id] = {
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "order_type": order_type,
            "limit_price": limit_price,
            "status": OrderStatus.PENDING,
            "filled_qty": 0,
            "avg_price": 0.0,
            "commission": 0.0,
            "created_at": now,
            "updated_at": now,
        }
        return order_id

    def get_order_status(self, order_id: str) -> dict:
        return self.orders.get(order_id, {"status": "unknown"})

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            order = self.orders[order_id]
            if order["status"] in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                order["status"] = OrderStatus.CANCELLED
                order["updated_at"] = datetime.now()
                return True
        return False

    def get_positions(self) -> dict[str, dict]:
        return {s: dict(p) for s, p in self.positions.items()}

    def get_balance(self) -> dict:
        return {"cash": self.cash, "total_value": self.current_value()}

    # ── 纸交易特有方法 ──

    def current_value(self) -> float:
        """当前总市值（现金 + 持仓市值，需要外部喂价格）"""
        return self.cash  # 持仓市值由外部 mark_to_market 计算

    def try_execute_pending(self, bar) -> list[str]:
        """
        尝试成交所有挂单

        Args:
            bar: MarketEvent 或 dict with symbol, close

        Returns:
            成交的 order_id 列表
        """
        executed = []
        for oid, order in list(self.orders.items()):
            if order["status"] not in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                continue
            if order["symbol"] != bar.symbol:
                continue

            fill_price = self._get_fill_price(order, bar.close)

            if order["direction"] == "LONG":
                # 买入
                qty = order["quantity"]
                cost = qty * fill_price * (1 + self.commission_rate)
                if self.cash >= cost:
                    self.cash -= cost
                    order["filled_qty"] = qty
                    order["avg_price"] = fill_price
                    order["commission"] = qty * fill_price * self.commission_rate
                    order["status"] = OrderStatus.FILLED
                    order["updated_at"] = datetime.now()

                    # 更新持仓
                    if bar.symbol in self.positions:
                        old_qty = self.positions[bar.symbol]["quantity"]
                        old_cost = self.positions[bar.symbol]["avg_cost"]
                        new_qty = old_qty + qty
                        new_cost = (old_cost * old_qty + fill_price * qty) / new_qty
                        self.positions[bar.symbol] = {"quantity": new_qty, "avg_cost": new_cost}
                    else:
                        self.positions[bar.symbol] = {"quantity": qty, "avg_cost": fill_price}

                    executed.append(oid)
                    self.trade_history.append({
                        "timestamp": datetime.now(),
                        "symbol": bar.symbol,
                        "direction": order["direction"],
                        "price": fill_price,
                        "quantity": qty,
                        "commission": order["commission"],
                    })

            elif order["direction"] == "EXIT":
                # 卖出
                pos = self.positions.get(bar.symbol, {"quantity": 0})
                qty = min(order["quantity"], pos["quantity"])
                if qty > 0:
                    revenue = qty * fill_price * (1 - self.commission_rate)
                    self.cash += revenue
                    order["filled_qty"] = qty
                    order["avg_price"] = fill_price
                    order["commission"] = qty * fill_price * self.commission_rate
                    order["status"] = OrderStatus.FILLED
                    order["updated_at"] = datetime.now()

                    self.positions[bar.symbol]["quantity"] -= qty
                    if self.positions[bar.symbol]["quantity"] <= 0:
                        del self.positions[bar.symbol]

                    executed.append(oid)
                    self.trade_history.append({
                        "timestamp": datetime.now(),
                        "symbol": bar.symbol,
                        "direction": order["direction"],
                        "price": fill_price,
                        "quantity": qty,
                        "commission": order["commission"],
                    })

        return executed

    def _get_fill_price(self, order: dict, close: float) -> float:
        """计算成交价（含滑点）"""
        if order["order_type"] == "LMT" and order["limit_price"] is not None:
            return order["limit_price"]
        # 市价单：买入贵一点，卖出贱一点
        if order["direction"] == "LONG":
            return close * (1 + self.slippage)
        else:
            return close * (1 - self.slippage)

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """按最新价计算总净值"""
        position_value = sum(
            p["quantity"] * prices.get(sym, p["avg_cost"])
            for sym, p in self.positions.items()
        )
        return self.cash + position_value
