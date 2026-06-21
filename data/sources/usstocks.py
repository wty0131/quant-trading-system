"""
美股数据源 — 基于 yfinance

特点：
  - 覆盖美股全部股票 + ETF + 港股（通过 .HK 后缀）
  - 需要 SOCKS5 代理（国内直连被封）
  - 数据质量高（Yahoo Finance 官方源）

用法:
    source = USStockSource()              # 自动读取 PROXY_SOCKS5 环境变量
    source = USStockSource(proxy='socks5://127.0.0.1:10808')  # 或显式指定
    df = source.get_history(['AAPL', 'TSLA', 'MSFT'], '2024-01-01', '2024-12-31')
"""

import os
import time
import pandas as pd
import yfinance as yf

from .base import DataSource


class USStockSource(DataSource):
    """美股数据源 — yfinance（需代理）"""

    market = "usstock"

    def __init__(self, proxy: str | None = None):
        """
        Args:
            proxy: SOCKS5 代理地址。None = 读 PROXY_SOCKS5 环境变量。
                   例: 'socks5://127.0.0.1:10808'
        """
        self._proxy = proxy or os.environ.get("PROXY_SOCKS5")
        if not self._proxy:
            print(
                "[USStockSource] 警告: 未配置代理。"
                "在国内网络下 yfinance 不可用。"
                "请在 .env 中设置 PROXY_SOCKS5=socks5://127.0.0.1:10808"
            )

    def _fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        从 Yahoo Finance 获取 OHLCV 数据

        symbol 格式: 'AAPL', 'TSLA', 'MSFT', 'BABA'
        港股: '0700.HK', '9988.HK'
        """
        if self._proxy:
            self._set_proxy()

        tk = yf.Ticker(symbol)
        df = tk.history(start=start, end=end)

        if self._proxy:
            self._clear_proxy()

        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        if "amount" not in df.columns:
            df["amount"] = df["close"] * df["volume"]

        return df[
            ["date", "open", "high", "low", "close", "volume", "amount"]
        ]

    def _set_proxy(self):
        """设置代理环境变量"""
        if self._proxy:
            os.environ["HTTP_PROXY"] = self._proxy
            os.environ["HTTPS_PROXY"] = self._proxy

    def _clear_proxy(self):
        """清除代理环境变量"""
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)

    def bulk_download(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "daily",
        callback=None,
    ) -> pd.DataFrame:
        """批量下载（带进度）"""
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
                time.sleep(0.3)  # 节制请求频率
            except Exception as e:
                print(f"  [{sym}] 失败: {type(e).__name__}: {e}")
        if callback:
            callback(total, total, "done")
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        return self._normalize(df, interval)
