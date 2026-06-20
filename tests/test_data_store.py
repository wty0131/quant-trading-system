"""
数据层端到端测试

验证链条：拉取真实数据 → 存入 SQLite → 读出 → 数据完整性检查
"""
import sys
import pandas as pd
from pathlib import Path

# 确保可以从项目根 import
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.sources.ashare import AShareSource
from data.store import DataStore
from data.schema import OHLCV_COLUMNS


def test_ashare_source():
    """测试 AShareSource 能拉取真实数据"""
    src = AShareSource()
    df = src.get_history(
        symbols=["sh.000300", "sh.600519"],
        start="2024-06-01",
        end="2024-06-30",
    )
    # 必须返回标准列
    assert not df.empty, "A股数据为空"
    assert list(df.columns) == OHLCV_COLUMNS, f"列不匹配: {df.columns.tolist()}"
    assert df["market"].iloc[0] == "ashare"
    assert df["symbol"].nunique() == 2
    assert df["date"].min() >= pd.Timestamp("2024-06-01")
    print(f"✓ AShareSource: {len(df)} rows, {df.symbol.nunique()} symbols")


def test_store_save_load():
    """测试存储层：写 → 读 → 校验"""
    import tempfile, os

    # 先拉数据
    src = AShareSource()
    df = src.get_history(
        symbols=["sh.000300"],
        start="2024-01-01",
        end="2024-06-30",
    )

    # 存
    db_path = Path(tempfile.gettempdir()) / "_test_quant.db"
    store = DataStore(str(db_path))
    store.save(df, "ashare", "daily")

    # 读
    loaded = store.load("ashare", "daily", symbols=["sh.000300"])
    assert not loaded.empty, "从数据库加载失败"
    assert len(loaded) == len(df), f"行数不一致: {len(loaded)} vs {len(df)}"
    assert abs(loaded["close"].sum() - df["close"].sum()) < 0.01

    # 检查 WAL 模式
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    wal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert wal.lower() == "wal", f"WAL模式未启用: {wal}"
    conn.close()

    # 清理
    os.remove(str(db_path))
    os.remove(str(db_path) + "-wal") if os.path.exists(str(db_path) + "-wal") else None
    os.remove(str(db_path) + "-shm") if os.path.exists(str(db_path) + "-shm") else None
    print(f"✓ DataStore: 存{len(df)}行 → 读{len(loaded)}行, WAL=ON")


def test_store_upsert():
    """测试 UPSERT 语义：重复存不增加行数"""
    import tempfile, os

    src = AShareSource()
    df = src.get_history(symbols=["sh.000300"], start="2024-03-01", end="2024-03-31")

    db_path = Path(tempfile.gettempdir()) / "_test_upsert.db"
    store = DataStore(str(db_path))

    # 存两次
    store.save(df, "ashare", "daily")
    before = store.load("ashare", "daily").shape[0]
    store.save(df, "ashare", "daily")
    after = store.load("ashare", "daily").shape[0]

    assert before == after, f"UPSERT 失效: {before} → {after}"

    os.remove(str(db_path))
    os.remove(str(db_path) + "-wal") if os.path.exists(str(db_path) + "-wal") else None
    os.remove(str(db_path) + "-shm") if os.path.exists(str(db_path) + "-shm") else None
    print(f"✓ UPSERT: 二次写入 {before}={after}")


def test_empty_handler():
    """测试空查询不崩"""
    store = DataStore("data/quant.db")
    df = store.load("ashare", "daily", symbols=["NOT_EXIST"])
    assert df.empty
    assert list(df.columns) == OHLCV_COLUMNS
    print(f"✓ 空查询安全: columns={OHLCV_COLUMNS}")


if __name__ == "__main__":
    print("=" * 50)
    print("量化数据层测试")
    print("=" * 50)
    test_ashare_source()
    test_store_save_load()
    test_store_upsert()
    test_empty_handler()
    print("=" * 50)
    print("全部通过 ✓")
