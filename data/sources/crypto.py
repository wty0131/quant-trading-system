"""
加密货币数据源 — 基于 ccxt

特点：
  - 支持 SOCKS5 代理（通过 v2rayN 等工具翻墙后拉取全量数据）
  - 自动探测可用交易所（直连 + 代理双通道）
  - 无需 API Key 即可拉取公开行情
"""

import time
import os
import pandas as pd
import ccxt

from .base import DataSource


# 直连优先（Gate.io 国内能通），代理交易所按已验证顺序排列
DIRECT_EXCHANGES = ["gate"]
PROXY_EXCHANGES = ["kraken", "coinbase", "bitfinex", "binance", "okx", "bybit"]


class CryptoSource(DataSource):
    """加密货币数据源 — ccxt（支持 SOCKS5 代理）"""

    market = "crypto"

    def __init__(self, exchange: str | None = None, proxy: str | None = None):
        """
        Args:
            exchange: 交易所 ID。None = 自动探测。
            proxy:    SOCKS5 代理地址。None = 读环境变量 PROXY_SOCKS5。
                      例: 'socks5://127.0.0.1:10808'
        """
        self._proxy = proxy or os.environ.get("PROXY_SOCKS5")
        if exchange is None:
            self._init_auto()
        else:
            self.exchange_name = exchange
            self._exchange = None

    def _init_auto(self):
        """自动探测：先直连，再代理"""
        # 第1轮：直连
        for name in DIRECT_EXCHANGES:
            try:
                ex = self._make_exchange(name, use_proxy=False)
                ex.load_markets()
                self.exchange_name = name
                self._exchange = ex
                print(f"[CryptoSource] 直连: {name}")
                return
            except Exception:
                continue

        # 第2轮：走代理
        if self._proxy:
            for name in PROXY_EXCHANGES:
                try:
                    ex = self._make_exchange(name, use_proxy=True)
                    ex.load_markets()
                    self.exchange_name = name
                    self._exchange = ex
                    print(f"[CryptoSource] 代理({self._proxy}): {name}")
                    return
                except Exception:
                    continue

        raise RuntimeError(
            f"无法连接任何加密货币交易所（直连+GATE+代理均失败）。"
        )

    def _make_exchange(self, name: str, use_proxy: bool):
        cls = getattr(ccxt, name)
        config = {"enableRateLimit": True, "timeout": 30000}
        if use_proxy and self._proxy:
            config["proxies"] = {
                "http": self._proxy,
                "https": self._proxy,
            }
        return cls(config)

    @property
    def exchange(self):
        if self._exchange is None:
            self._exchange = self._make_exchange(
                self.exchange_name,
                use_proxy=(self._proxy is not None and self.exchange_name not in DIRECT_EXCHANGES),
            )
        return self._exchange

    def _fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """获取 OHLCV 历史数据"""
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
            since = ohlcv[-1][0] + 86400000

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
        self, symbols: list[str], start: str, end: str,
        interval: str = "daily", callback=None,
    ) -> pd.DataFrame:
        """批量下载（带进度回调）"""
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
                time.sleep(0.5)
            except Exception as e:
                print(f"  [{sym}] 失败: {e}")
        if callback:
            callback(total, total, "done")
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        return self._normalize(df, interval)
