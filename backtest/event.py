"""
事件类型定义 — 回测引擎的信息载体

四种事件：
  MarketEvent  — 新K线到达（DataHandler产出）
  SignalEvent  — 策略生成交易信号（Strategy产出）
  OrderEvent   — 待执行订单（Portfolio产出）
  FillEvent    — 订单成交回报（ExecutionHandler产出）

事件驱动的前提：一切信息以事件形式流转。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"


class OrderType(str, Enum):
    MKT = "MKT"  # 市价单
    LMT = "LMT"  # 限价单（预留）


@dataclass
class MarketEvent:
    """新K线到达 — 每个交易日触发一次"""
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_row(cls, row: dict[str, Any]):
        """从 DataFrame 的一行创建 MarketEvent"""
        return cls(
            timestamp=row["date"],
            symbol=row.get("symbol", ""),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)),
        )


@dataclass
class SignalEvent:
    """策略生成的交易信号"""
    timestamp: datetime
    symbol: str
    direction: Direction
    strength: float = 1.0  # 0~1，信号强度（预留）


@dataclass
class OrderEvent:
    """待执行的订单"""
    timestamp: datetime
    symbol: str
    direction: Direction
    order_type: OrderType = OrderType.MKT
    quantity: int = 0


@dataclass
class FillEvent:
    """订单成交回报"""
    timestamp: datetime
    symbol: str
    direction: Direction
    quantity: int
    price: float
    commission: float = 0.0
