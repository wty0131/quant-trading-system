"""
订单管理系统 (OMS) — 订单状态机

状态流转:
  submit_order()
       │
       ▼
  PENDING ──→ timeout → CANCELLED
       │
       ▼
  PARTIAL_FILLED ──→ timeout → CANCELLED (撤剩余)
       │
       ▼
  FILLED (终态)

每根 K 线到达时:
  1. 尝试成交所有挂单 (broker.try_execute_pending)
  2. 检查超时挂单
  3. 返回成交列表

这比回测引擎的 ExecutionHandler 复杂——回测假设立即成交，
实盘的订单有独立的生命周期。
"""

from datetime import datetime, timedelta
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderManager:
    """
    订单管理器

    职责:
      - 提交订单到 Broker
      - 跟踪所有未完成订单
      - 超时撤单
      - 记录成交
    """

    def __init__(
        self,
        broker,             # Broker 实例 (PaperBroker / CCXTBroker / ...)
        timeout_seconds: int = 300,   # 5分钟超时
        max_retries: int = 2,         # 最大重试次数
    ):
        self.broker = broker
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._pending: dict[str, dict] = {}       # 所有未完成订单
        self._history: list[dict] = []             # 已完成/已取消

    def submit(
        self, symbol: str, direction: str, quantity: int,
        order_type: str = "MKT", limit_price: float | None = None,
    ) -> str:
        """
        提交订单

        Returns:
            order_id
        """
        oid = self.broker.submit_order(
            symbol=symbol, direction=direction, quantity=quantity,
            order_type=order_type, limit_price=limit_price,
        )
        meta = {
            "order_id": oid,
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "submitted_at": datetime.now(),
            "retries": 0,
        }
        self._pending[oid] = meta
        return oid

    def update(self, bar) -> list[dict]:
        """
        每根 bar 来时调用:
          1. 尝试成交
          2. 检查超时

        Returns:
            最近成交的订单列表
        """
        # 1. 尝试成交
        fills = self.broker.try_execute_pending(bar) if hasattr(self.broker, "try_execute_pending") else []

        # 2. 从 pending 移走已完成的
        for oid in fills:
            self._move_to_history(oid)

        # 3. 检查超时
        now = datetime.now()
        for oid, meta in list(self._pending.items()):
            elapsed = (now - meta["submitted_at"]).total_seconds()
            if elapsed > self.timeout_seconds:
                if meta["retries"] < self.max_retries:
                    # 重试
                    meta["retries"] += 1
                    meta["submitted_at"] = now
                else:
                    # 放弃
                    self.broker.cancel_order(oid)
                    self._move_to_history(oid)

        return fills

    def _move_to_history(self, oid: str):
        """归档已完成的订单"""
        if oid in self._pending:
            self._history.append(self._pending.pop(oid))

    @property
    def active_count(self) -> int:
        return len(self._pending)

    @property
    def fill_history(self) -> list[dict]:
        return self._history

    def get_order(self, order_id: str) -> dict | None:
        if order_id in self._pending:
            return self._pending[order_id]
        # 从 broker 查最新状态
        return self.broker.get_order_status(order_id)
