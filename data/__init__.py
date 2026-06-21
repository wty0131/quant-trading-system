"""
量化交易系统 — 数据层

多市场统一数据接口：
  - DataSource(ABC) — 抽象基类
  - AShareSource    — A股数据源 (baostock)
  - CryptoSource    — 加密数据源 (ccxt)
  - DataStore       — SQLite 存储层
"""

from .sources.base import DataSource
from .sources.ashare import AShareSource
from .sources.crypto import CryptoSource
from .sources.usstocks import USStockSource
from .store import DataStore
from .schema import OHLCV_COLUMNS, OHLCV_DTYPES

__all__ = [
    "DataSource",
    "AShareSource",
    "CryptoSource",
    "USStockSource",
    "DataStore",
    "OHLCV_COLUMNS",
    "OHLCV_DTYPES",
]
