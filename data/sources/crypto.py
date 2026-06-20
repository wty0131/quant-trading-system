"""
加密货币数据源 — 基于 ccxt

特点：
  - 覆盖 100+ 交易所（Binance, OKX, Bybit, Coinbase...）
  - 无需 API Key 即可拉取公开行情
  - 24/7 交易，没有停牌/涨跌停

注意：
  - 默认用 Binance（流动性最好、数据最全）
  - ccxt 拉取大时间跨度日线需要分片（限制约 1000 条/次）
  - 加密市场节假日不休，freq='B' 不可用
"""

import pandas as pd
import ccxt

from .base import DataSource


class CryptoSource(DataSource):
    """加密货币数据源 — ccxt (Binance)"""

    market = "crypto"

    def __init__(self, exchange: str = "binance"):
        """
        Args:
            exchange: 交易所 ID（ccxt 格式，如 'binance', 'okx', 'bybit'）
        """
        self.exchange_name = exchange
        self._exchange = None

    @property
    def exchange(self):
        """懒加载交易所实例"""
        if self._exchange is None:
            cls = getattr(ccxt, self.exchange_name)
            self._exchange = cls({
                "enableRateLimit": True,  # ccxt 内置频率限制
                "timeout": 30000,
            })
        return self._exchange

    def _fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        从交易所获取 OHLCV 数据

        symbol 格式: 'BTC/USDT', 'ETH/USDT'
        """
        since = self.exchange.parse8601(f"{start}T00:00:00Z")
        end_ts = self.exchange.parse8601(f"{end}T23:59:59Z")

        all_ohlcv = []

        while since < end_ts:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, timeframe="1d", since=since, limit=1000
            )
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            # 下一次从最后一条的时间戳 + 1天开始
            since = ohlcv[-1][0] + 86400000  # ms → +1 day

        if not all_ohlcv:
            return pd.DataFrame()

        df = pd.DataFrame(
            all_ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["amount"] = df["close"] * df["volume"]  # 估算成交额
        df = df[df["date"].between(pd.Timestamp(start), pd.Timestamp(end))]

        return df[["date", "open", "high", "low", "close", "volume", "amount"]]

    def get_tickers(self) -> dict:
        """获取所有交易对行情快照"""
        return self.exchange.fetch_tickers()
