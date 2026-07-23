"""
增量数据缓存 — SQLite + baostock

首次拉取全量存 SQLite, 之后只拉新日期。
纸交易引擎和回测页共用此缓存。
"""
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
from .store import DataStore
from .sources.ashare import AShareSource


class CachedFetcher:
    """带 SQLite 缓存的数据获取器"""

    def __init__(self, db_path="data/quant.db"):
        self.store = DataStore(db_path)
        self.source = AShareSource()

    def get(
        self, symbols: list[str], start: str, end: str
    ) -> pd.DataFrame:
        """
        获取 OHLCV 数据（优先从 SQLite 缓存读取，缺失部分才拉取）
        """
        # 1. 从缓存读取
        cached = self.store.load("ashare", "daily", symbols=symbols, start=start, end=end)

        # 2. 找出缺失的 symbol
        cached_syms = set(cached["symbol"].unique()) if not cached.empty else set()
        missing_syms = [s for s in symbols if s not in cached_syms]

        # 3. 找出每个 sym 的最新日期 → 只拉增量
        need_pull = []
        for sym in symbols:
            if sym in cached_syms:
                sym_data = cached[cached["symbol"] == sym]
                last_date = str(sym_data["date"].max().date())
                if last_date < end:
                    need_pull.append((sym, last_date, end))
            else:
                need_pull.append((sym, start, end))

        if not need_pull:
            return cached

        # 4. 只拉取缺失部分
        new_frames = []
        for sym, s, e in need_pull:
            try:
                df = self.source.get_history([sym], s, e)
                if not df.empty:
                    new_frames.append(df)
            except Exception:
                pass

        if new_frames:
            fresh = pd.concat(new_frames, ignore_index=True)
            # 5. 合并 + 存入缓存
            merged = pd.concat([cached, fresh], ignore_index=True).drop_duplicates(
                subset=["symbol", "date"]
            )
            self.store.save(merged, "ashare", "daily")
            return merged

        return cached

    def prefetch_all(self, symbols: list[str], start="2026-01-01"):
        """批量预热缓存(一次性全拉)"""
        end = (date.today() - timedelta(days=1)).isoformat()
        print(f"🔄 预热缓存 {len(symbols)} 只 {start}~{end} ...")
        batch_size = 10
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            try:
                df = self.source.get_history(batch, start, end)
                if not df.empty:
                    self.store.save(df, "ashare", "daily")
            except Exception:
                pass
            if (i + batch_size) % 100 == 0:
                print(f"  {min(i + batch_size, len(symbols))}/{len(symbols)}")
        print(f"✓ 缓存完成")
