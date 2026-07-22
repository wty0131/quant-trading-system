"""
量化交易系统 — 数据层

A股数据接口：
  - DataSource(ABC) — 抽象基类
  - AShareSource    — A股数据源 (baostock)
  - DataStore       — SQLite 存储层
"""

from .sources.base import DataSource
from .sources.ashare import AShareSource
from .store import DataStore
from .schema import OHLCV_COLUMNS, OHLCV_DTYPES

__all__ = [
    "DataSource",
    "AShareSource",
    "DataStore",
    "OHLCV_COLUMNS",
    "OHLCV_DTYPES",
]
