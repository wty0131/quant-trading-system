"""
加密货币数据源 — 基于 ccxt

特点：
  - 覆盖 100+ 交易所，自动探测可用交易所（适应国内网络限制）
  - 无需 API Key 即可拉取公开行情
  - 24/7 交易，没有停牌/涨跌停
  - 支持批量下载 + 进度回调

注意：
  - 国内直连 Binance/OKX 通常被墙，自动 fallback 到 Gate.io
  - ccxt 拉取大时间跨度日线需要分片（限制约 1000 条/次）
  - 加密市场节假日不休
"""

import time
import pandas as pd
import ccxt

from .base import DataSource


# 交易所优先级列表（国内网络最优选择排前面）
EXCHANGE_PRIORITY = ["gate", "binance", "okx", "bybit", "kraken"]


def _detect_exchange():
    """自动探测国内网络可达的交易所"""
    for name in EXCHANGE_PRIORITY:
        try:
            cls = getattr(ccxt, name)
            ex = cls({"enableRateLimit": True, "timeout": 15000})
            ex.load_markets()
            return name, ex
        except Exception:
            continue
    raise RuntimeError(
        f"无法连接任何交易所，已尝试: {EXCHANGE_PRIORITY}。请检查网络。"
    )


class CryptoSource(DataSource):
    """加密货币数据源 — ccxt（自动探测可用交易所）"""

    market = "crypto"

    def __init__(self, exchange: str | None = None):
        """
        Args:
            exchange: 交易所 ID。None = 自动探测国内可用交易所。
                      可指定: 'gate', 'binance', 'okx', 'bybit' 等
        """
        if exchange is None:
            name, ex = _detect_exchange()
            self.exchange_name = name
            self._exchange = ex
            print(f"[CryptoSource] 自动选择交易所: {name}")
        else:
            self.exchange_name = exchange
            self._exchange = None

    @property
    def exchange(self):
        if self._exchange is None:
            cls = getattr(ccxt, self.exchange_name)
            self._exchange = cls({
                "enableRateLimit": True,
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
            since = ohlcv[-1][0] + 86400000  # +1 天（毫秒）

        if not all_ohlcv:
            return pd.DataFrame()

        df = pd.DataFrame(
            all_ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["amount"] = df["close"] * df["volume"]
        df = df[df["date"].between(pd.Timestamp(start), pd.Timestamp(end))]

        return df[["date", "open", "high", "low", "close", "volume", "amount"]]

    def bulk_download(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "daily",
        callback=None,
    ) -> pd.DataFrame:
        """
        批量下载（带进度回调，适合大批量拉取）

        Args:
            symbols:  交易对列表
            start:    起始日期
            end:      结束日期
            interval: K线周期
            callback: 进度回调 callback(current, total, symbol)

        Returns:
            标准 OHLCV DataFrame
        """
        frames = []
        total = len(symbols)

        for i, sym in enumerate(symbols):
            if callback:
                callback(i, total, sym)
            try:
                raw = self._fetch(sym, start, end)
                if not raw.empty:
                    raw["symbol"] = sym
                    frames.append(raw)
                time.sleep(0.5)  # 节制请求频率
            except Exception as e:
                print(f"  [{sym}] 拉取失败: {e}")

        if callback:
            callback(total, total, "done")

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        return self._normalize(df, interval)
