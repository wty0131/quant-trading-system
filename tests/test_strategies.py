"""策略库集成测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from backtest.engine import BacktestEngine
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy


def _get_test_data(days=500) -> pd.DataFrame:
    """生成含多重市场形态的测试数据"""
    np.random.seed(42)
    returns = np.zeros(days)
    for i in range(days):
        if i < 100:   returns[i] = np.random.normal(0.0003, 0.012)  # 震荡
        elif i < 250: returns[i] = np.random.normal(0.0010, 0.010)  # 上涨
        elif i < 350: returns[i] = np.random.normal(-0.0008, 0.015) # 下跌
        else:         returns[i] = np.random.normal(0.0001, 0.008)  # 恢复
    close = 100 * np.exp(np.cumsum(returns))
    dates = pd.date_range("2023-01-02", periods=days, freq="B")

    return pd.DataFrame({
        "symbol": "TEST", "date": dates,
        "open": close * 0.995, "high": close * 1.015,
        "low": close * 0.985, "close": close,
        "volume": np.abs(np.random.randn(days) * 1e8 + 2e8).astype(int),
        "amount": close * 1e8, "market": "test", "interval": "daily",
    })


def test_bollinger():
    df = _get_test_data()
    engine = BacktestEngine(df, BollingerStrategy(period=20, k=2.0), 1_000_000,
                           slippage=0.001, commission_rate=0.0003)
    r = engine.run()
    print(f"Bollinger: return={r.total_return*100:.2f}% trades={r.total_trades} "
          f"sharpe={r.sharpe_ratio:.3f} MDD={r.max_drawdown*100:.2f}%")
    assert r.total_trades > 0, "应产生交易"
    assert -1 < r.total_return < 5, "收益在合理范围"
    print("✓ 布林带")


def test_turtle():
    df = _get_test_data(500)
    engine = BacktestEngine(df, TurtleStrategy(entry_period=10, exit_period=5,
                            atr_period=14, atr_stop=2.0), 1_000_000,
                            slippage=0.001, commission_rate=0.0003)
    r = engine.run()
    print(f"Turtle: return={r.total_return*100:.2f}% trades={r.total_trades} "
          f"win_rate={r.win_rate*100:.1f}% profit_factor={r.profit_factor:.2f} "
          f"sharpe={r.sharpe_ratio:.3f}")
    assert r.total_trades > 0
    assert -1 < r.total_return < 5
    print("✓ 海龟")


def test_rsrs():
    df = _get_test_data(300)
    engine = BacktestEngine(df, RSRSStrategy(window=18, buy_threshold=0.5, sell_threshold=-0.5),
                            1_000_000, slippage=0.001, commission_rate=0.0003)
    r = engine.run()
    print(f"RSRS: return={r.total_return*100:.2f}% trades={r.total_trades} "
          f"sharpe={r.sharpe_ratio:.3f}")
    assert r.total_trades > 0
    print("✓ RSRS")


def test_all_on_real_data():
    """用真实A股数据做端到端检验"""
    from data.sources.ashare import AShareSource
    from data.store import DataStore
    import os, tempfile

    ashare = AShareSource()
    df = ashare.get_history(["sh.000300"], "2024-01-01", "2024-12-31")

    db_path = Path(tempfile.gettempdir()) / "_test_strat.db"
    store = DataStore(str(db_path))
    store.save(df, "ashare", "daily")
    df_loaded = store.load("ashare", "daily", symbols=["sh.000300"])

    for name, strategy in [
        ("bollinger", BollingerStrategy(20, 2.0)),
        ("turtle", TurtleStrategy(20, 10, 20, 2.0)),
        ("rsrs", RSRSStrategy(18, 0.5, -0.5)),
    ]:
        engine = BacktestEngine(df_loaded, strategy, 1_000_000, 0.001, 0.0003)
        r = engine.run()
        print(f"  {name:12s} CSI300 2024: return={r.total_return*100:6.2f}%  "
              f"sharpe={r.sharpe_ratio:6.3f}  MDD={r.max_drawdown*100:6.2f}%  trades={r.total_trades}")
        assert r.total_trades > 0, f"{name} 无交易"

    for f in [db_path, str(db_path)+"-wal", str(db_path)+"-shm"]:
        try: os.remove(f)
        except: pass
    print("✓ 真实数据端到端")


if __name__ == "__main__":
    print("=" * 55)
    test_bollinger()
    test_turtle()
    test_rsrs()
    print()
    print("--- 真实数据 ---")
    test_all_on_real_data()
    print("=" * 55)
    print("ALL TESTS PASSED")
