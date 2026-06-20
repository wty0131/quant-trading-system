"""
SQLite 数据存储层

表命名规则: {market}_{interval}
  例: ashare_daily, crypto_daily, ashare_weekly

设计要点：
  - WAL 模式：避免读写锁冲突（CPA项目踩过的坑）
  - UPSERT 语义：同(symbol, date)新数据覆盖旧数据
  - 不引入 ORM：pandas to_sql/read_sql 足够直接
"""

import sqlite3
import pandas as pd
from pathlib import Path

from .schema import OHLCV_COLUMNS


class DataStore:
    """SQLite 数据存储"""

    def __init__(self, db_path: str = "data/quant.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")      # 写前日志，避免锁
        conn.execute("PRAGMA synchronous=NORMAL")     # 性能与安全的平衡
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        """初始化数据库 — 只创建元数据表"""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _tables_meta (
                    table_name TEXT PRIMARY KEY,
                    market     TEXT NOT NULL,
                    interval   TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    rows       INTEGER DEFAULT 0
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _table_name(self, market: str, interval: str) -> str:
        return f"{market}_{interval}"

    def _ensure_table(self, conn: sqlite3.Connection, market: str, interval: str):
        """确保数据表存在，不存在则创建"""
        table = self._table_name(market, interval)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                symbol   TEXT NOT NULL,
                date     TEXT NOT NULL,
                open     REAL,
                high     REAL,
                low      REAL,
                close    REAL,
                volume   REAL DEFAULT 0,
                amount   REAL DEFAULT 0,
                market   TEXT DEFAULT '{market}',
                interval TEXT DEFAULT '{interval}',
                PRIMARY KEY (symbol, date)
            )
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table}_date
            ON {table}(date)
        """)
        # 同步元数据
        conn.execute("""
            INSERT OR REPLACE INTO _tables_meta (table_name, market, interval)
            VALUES (?, ?, ?)
        """, (table, market, interval))

    def save(self, df: pd.DataFrame, market: str, interval: str):
        """
        存储数据 — UPSERT 语义

        Args:
            df: 标准 OHLCV DataFrame
            market:  市场标识
            interval: K线周期
        """
        if df.empty:
            return

        table = self._table_name(market, interval)
        conn = self._get_conn()
        try:
            self._ensure_table(conn, market, interval)

            # 确保日期是字符串（SQLite 友好）
            save_df = df.copy()
            save_df["date"] = save_df["date"].astype(str)

            # 只存标准列
            cols = [c for c in OHLCV_COLUMNS if c in save_df.columns]
            save_df = save_df[cols]

            # pandas to_sql with replace on duplicates
            # 先删旧数据再 insert
            symbols = save_df["symbol"].unique()
            dates = save_df["date"].unique()
            placeholders_s = ",".join(["?"] * len(symbols))
            placeholders_d = ",".join(["?"] * len(dates))
            conn.execute(
                f"DELETE FROM {table} WHERE symbol IN ({placeholders_s}) AND date IN ({placeholders_d})",
                list(symbols) + list(dates),
            )

            save_df.to_sql(table, conn, if_exists="append", index=False)

            # 更新行数元数据
            row_count = pd.read_sql(f"SELECT COUNT(*) as n FROM {table}", conn)["n"][0]
            conn.execute(
                "UPDATE _tables_meta SET rows = ? WHERE table_name = ?",
                (row_count, table),
            )

            conn.commit()
        finally:
            conn.close()

    def load(
        self,
        market: str,
        interval: str,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """
        从数据库载入数据

        Args:
            market:   市场标识
            interval: K线周期
            symbols:  品种列表（None = 全部）
            start:    起始日期 "YYYY-MM-DD"
            end:      结束日期 "YYYY-MM-DD"

        Returns:
            标准 OHLCV DataFrame
        """
        table = self._table_name(market, interval)
        conn = self._get_conn()
        try:
            # 检查表是否存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cursor.fetchone() is None:
                return pd.DataFrame(columns=OHLCV_COLUMNS)

            query = f"SELECT * FROM {table} WHERE 1=1"
            params = []

            if symbols:
                placeholders = ",".join(["?"] * len(symbols))
                query += f" AND symbol IN ({placeholders})"
                params.extend(symbols)
            if start:
                query += " AND date >= ?"
                params.append(start)
            if end:
                query += " AND date <= ?"
                params.append(end)

            query += " ORDER BY symbol, date"

            df = pd.read_sql(query, conn, params=params)

            if df.empty:
                return pd.DataFrame(columns=OHLCV_COLUMNS)

            df["date"] = pd.to_datetime(df["date"])
            return df

        finally:
            conn.close()

    def list_tables(self) -> pd.DataFrame:
        """列出所有数据表"""
        conn = self._get_conn()
        try:
            return pd.read_sql(
                "SELECT * FROM _tables_meta ORDER BY market, interval",
                conn,
            )
        finally:
            conn.close()

    def get_symbols(self, market: str, interval: str) -> list[str]:
        """获取某表中的所有 symbol"""
        table = self._table_name(market, interval)
        conn = self._get_conn()
        try:
            cursor = conn.execute(f"SELECT DISTINCT symbol FROM {table}")
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
