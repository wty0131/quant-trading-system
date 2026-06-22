"""
量化交易系统 — 策略库

6个经典策略：
  DualMAStrategy  — 双均线交叉（backtest/strategy.py）
  BollingerStrategy — 布林带突破
  TurtleStrategy    — 海龟交易系统
  RSRSStrategy      — 阻力支撑相对强度
  MultiFactorStrategy — 多因子选股
  PairsStrategy     — 配对交易
"""

from backtest.strategy import DualMAStrategy
from .bollinger import BollingerStrategy
from .turtle import TurtleStrategy
from .rsrs import RSRSStrategy
from .multifactor import MultiFactorStrategy
from .pairs import PairsStrategy

__all__ = [
    "DualMAStrategy",
    "BollingerStrategy",
    "TurtleStrategy",
    "RSRSStrategy",
    "MultiFactorStrategy",
    "PairsStrategy",
]
