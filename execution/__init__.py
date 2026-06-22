"""
量化交易系统 — 执行层

从回测到实盘的桥梁:
  Broker(ABC)      — 券商统一接口 (纸交易/CCXT/QMT)
  OrderManager     — 订单状态机 (submit→pending→partial→filled)
  PaperBroker      — 纸交易模拟成交 (立刻可用)
  CCXTBroker       — 加密实盘 (Gate.io via proxy)
  QMTBroker        — A股实盘 (需券商开通QMT权限)
  RiskGuard        — 独立风控守护 (不与策略同进程)
  PaperTradingEngine — 纸交易主循环 (实时版BacktestEngine)
"""

from .broker import Broker
from .paper_broker import PaperBroker
from .ccxt_broker import CCXTBroker
from .qmt_broker import QMTBroker
from .oms import OrderManager, OrderStatus
from .risk_guard import RiskGuard
from .paper_engine import PaperTradingEngine

__all__ = [
    "Broker",
    "PaperBroker",
    "CCXTBroker",
    "QMTBroker",
    "OrderManager",
    "OrderStatus",
    "RiskGuard",
    "PaperTradingEngine",
]
