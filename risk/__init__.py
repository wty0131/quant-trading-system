"""
量化交易系统 — 风控与组合管理

四个模块:
  sizing.py   — 仓位管理 (固定/Kelly/风险平价/波动率目标)
  stops.py    — 止损系统 (固定/ATR/移动/时间)
  allocator.py — 资金分配 (等权/波动率倒数/Markowitz)
  combiner.py  — 多策略组合引擎
"""

from .sizing import FixedFractionSizer, KellySizer, VolTargetSizer
from .stops import FixedStop, ATRStop, TrailingStop, TimeStop, StopManager
from .allocator import EqualAllocator, InvVolAllocator, MaxSharpeAllocator
from .combiner import StrategyCombiner

__all__ = [
    "FixedFractionSizer",
    "KellySizer",
    "VolTargetSizer",
    "FixedStop",
    "ATRStop",
    "TrailingStop",
    "TimeStop",
    "StopManager",
    "EqualAllocator",
    "InvVolAllocator",
    "MaxSharpeAllocator",
    "StrategyCombiner",
]
