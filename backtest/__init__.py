"""
量化交易系统 — 回测引擎

事件驱动架构，模拟实盘逻辑：
  MarketEvent  → Strategy.on_bar() → SignalEvent
  SignalEvent  → Portfolio         → OrderEvent
  OrderEvent   → ExecutionHandler  → FillEvent
  FillEvent    → Portfolio.update()→ 更新持仓/净值
"""

from .engine import BacktestEngine
from .strategy import Strategy, BuyAndHoldStrategy
from .event import MarketEvent, SignalEvent, OrderEvent, FillEvent
from .portfolio import Portfolio
from .execution import ExecutionHandler
from .analytics import generate_report

__all__ = [
    "BacktestEngine",
    "Strategy",
    "BuyAndHoldStrategy",
    "MarketEvent",
    "SignalEvent",
    "OrderEvent",
    "FillEvent",
    "Portfolio",
    "ExecutionHandler",
    "generate_report",
]
