"""
数据源抽象基类 — 所有市场数据源的统一契约

设计理念：
  每一个市场（A股/加密/美股）只需实现 _fetch() 方法，
  框架自动处理：标准化 → 清洗 → 去重 → 排序 → 类型校验。

子类必须实现：
  _fetch(symbol, start, end) → pd.DataFrame(columns=COLUMNS)
  market 属性返回市场标识字符串
"""

from abc import ABC, abstractmethod
import pandas as pd
import logging

from ..schema import OHLCV_COLUMNS

logger = logging.getLogger(__name__)


class DataSource(ABC):
    """
    数据源抽象基类

    用法:
        class MySource(DataSource):
            market = "mymarket"

            def _fetch(self, symbol, start, end):
                ...  # 从某处拉数据
                return raw_df

        src = MySource()
        df = src.get_history(["sym1", "sym2"], "2024-01-01", "2024-12-31")
    """

    # ── 子类必须定义 ──
    @property
    @abstractmethod
    def market(self) -> str:
        """市场标识: 'ashare' / 'crypto' / 'usstock'"""
        ...

    @abstractmethod
    def _fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        原始数据获取 — 由子类实现

        Args:
            symbol: 品种代码（子类定义格式）
            start:  起始日期 "YYYY-MM-DD"
            end:    结束日期 "YYYY-MM-DD"

        Returns:
            pd.DataFrame，至少包含 [date, open, high, low, close, volume, amount]
        """
        ...

    # ── 框架方法（子类通常不需要覆盖）──
    def get_history(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "daily",
    ) -> pd.DataFrame:
        """
        获取历史数据（批量symbol，统一输出）

        Args:
            symbols:  品种列表，如 ["sh.000300", "sh.600519"]
            start:    起始日期
            end:      结束日期
            interval: K线周期

        Returns:
            标准 OHLCV DataFrame，列: [symbol, date, open, high, low, close,
                                       volume, amount, market, interval]
        """
        all_frames = []
        failed = []

        for sym in symbols:
            try:
                raw = self._fetch(sym, start, end)
                if raw.empty:
                    failed.append((sym, "空数据"))
                    continue
                raw["symbol"] = sym
                all_frames.append(raw)
            except Exception as e:
                logger.warning(f"获取 {sym} 失败: {e}")
                failed.append((sym, str(e)))

        if failed:
            logger.warning(
                f"{len(failed)}/{len(symbols)} 只失败: "
                + ", ".join(f"{s}[{r[:30]}]" for s, r in failed)
            )

        if not all_frames:
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        # 合并 + 标准化
        df = pd.concat(all_frames, ignore_index=True)
        df = self._normalize(df, interval)
        return df

    def _normalize(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """标准化：统一列名、类型、排序、去重"""
        # 统一列名
        df = df.rename(columns={
            "timestamp": "date",
            "datetime": "date",
            "vol": "volume",
            "turnover": "amount",
        })

        # 确保必要列存在
        required = ["date", "open", "high", "low", "close"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"数据缺少必要列: {col}")

        # 类型转换
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)
        df["amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0)

        # 添加元数据
        df["market"] = self.market
        df["interval"] = interval
        if "symbol" not in df.columns:
            df["symbol"] = "unknown"

        # 去重 + 排序
        df = df.drop_duplicates(subset=["symbol", "date"]).sort_values(
            ["symbol", "date"]
        ).reset_index(drop=True)

        # 确保列顺序
        existing = [c for c in OHLCV_COLUMNS if c in df.columns]
        return df[existing]
