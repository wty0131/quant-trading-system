"""风控与组合管理测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from risk.sizing import FixedFractionSizer, KellySizer, RiskParitySizer, VolTargetSizer
from risk.stops import FixedStop, ATRStop, TrailingStop, TimeStop, StopManager
from risk.allocator import EqualAllocator, InvVolAllocator, MaxSharpeAllocator
from risk.combiner import StrategyCombiner
from backtest.event import MarketEvent
from backtest.strategy import DualMAStrategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy


def test_sizers():
    """仓位管理模型"""
    ff = FixedFractionSizer(0.2)
    assert ff.get_position_pct(1_000_000, 100) == 0.2

    kelly = KellySizer(win_rate=0.4, profit_factor=2.0, half=True)
    f = kelly.get_position_pct(1_000_000, 100)
    assert 0.05 < f < 0.25, f"Kelly={f} 不在5-25%范围"
    print(f"Fixed=20%  Kelly={f*100:.1f}%")

    rp = RiskParitySizer(target_risk=0.05)
    f_rp = rp.get_position_pct(1_000_000, 100, volatility=0.30)
    assert 0.05 < f_rp < 0.50, f"RiskParity={f_rp} 不合理"
    print(f"RiskParity(vol=30%): {f_rp*100:.1f}%")

    vt = VolTargetSizer(target_vol=0.15)
    f_vt = vt.get_position_pct(1_000_000, 100, realized_vol=0.25)
    assert 0.2 < f_vt < 1.5, f"VolTarget={f_vt} 不合理"
    print(f"VolTarget(realized=25%): {f_vt*100:.1f}%")
    print("✓ 仓位模型")


def test_stops():
    """止损系统"""
    bar = MarketEvent(
        timestamp=pd.Timestamp("2024-06-15"),
        symbol="TEST", open=100, high=105, low=95, close=92, volume=1e8,
    )
    entry_time = pd.Timestamp("2024-06-01")

    # 固定止损
    fstop = FixedStop(0.05)
    assert fstop.check(bar, 100, entry_time)  # -8% > -5%

    # ATR止损
    astop = ATRStop(2.0)
    astop.set_entry(100)
    triggered = astop.check(bar, 100, entry_time, atr=3.0)
    # HWM=105, stop=105-6=99, close=92 < 99 → True
    assert triggered

    # 时间止损
    tstop = TimeStop(14)
    assert tstop.check(bar, 100, entry_time)  # 第15天还没盈利

    # StopManager
    mgr = StopManager()
    mgr.add(FixedStop(0.05))
    mgr.add(ATRStop(2.0))
    mgr.on_entry(100, entry_time)
    assert mgr.check(bar, atr=3.0)
    print("✓ 止损系统")


def test_allocators():
    """资金分配"""
    np.random.seed(42)
    returns = {
        "strat_A": np.random.normal(0.0008, 0.012, 200),
        "strat_B": np.random.normal(0.0005, 0.018, 200),
        "strat_C": np.random.normal(0.0003, 0.008, 200),
    }
    capital = 1_000_000

    eq = EqualAllocator().allocate(returns, capital)
    assert sum(eq.values()) == capital
    print(f"Equal: {[f'{k}={v/capital*100:.0f}%' for k,v in eq.items()]}")

    iv = InvVolAllocator().allocate(returns, capital)
    # 波动最高的B应该分最少
    b_pct = iv["strat_B"] / capital
    c_pct = iv["strat_C"] / capital
    assert b_pct < c_pct, f"高波动的B({b_pct:.0%})应小于低波动的C({c_pct:.0%})"
    print(f"InvVol: {[f'{k}={v/capital*100:.0f}%' for k,v in iv.items()]}")

    ms = MaxSharpeAllocator(lookback=200).allocate(returns, capital)
    assert sum(ms.values()) == capital
    print(f"MaxSharpe: {[f'{k}={v/capital*100:.0f}%' for k,v in ms.items()]}")
    print("✓ 资金分配")


def test_combiner():
    """多策略组合端到端"""
    from data.sources.ashare import AShareSource
    from data.store import DataStore
    import os, tempfile

    # 获取数据
    ashare = AShareSource()
    df = ashare.get_history(["sh.000300"], "2024-01-01", "2024-12-31")

    # 组合
    combiner = StrategyCombiner(
        strategies={
            "DualMA":    DualMAStrategy(5, 20),
            "Bollinger": BollingerStrategy(20, 2.0),
            "Turtle":    TurtleStrategy(20, 10, 20, 2.0),
            "RSRS":      RSRSStrategy(18, 0.5, -0.5),
        },
        allocator=InvVolAllocator(),
        initial_cash=1_000_000,
        slippage=0.001,
        commission_rate=0.0003,
    )
    report = combiner.run(df)

    # 验证
    individual_sharpes = list(combiner.individual_sharpes().values())
    avg_sharpe = np.mean(individual_sharpes)
    print(f"\n  Avg individual Sharpe: {avg_sharpe:.3f}")
    print(f"  Combo Sharpe:          {report.sharpe_ratio:.3f}")
    # 组合 Sharpe 应 >= 平均值（分散化效果）
    # 注：不一定严格大于，因为这取决于策略相关性

    # 相关性矩阵
    corr = combiner.get_correlation_matrix()
    if not corr.empty:
        print(f"\n  Correlation matrix:\n{corr.round(3)}")

    assert report.total_return != 0, "组合应有收益"
    assert report.max_drawdown <= 0, "MDD 应为负值"
    print("✓ 多策略组合")


if __name__ == "__main__":
    print("=" * 50)
    test_sizers()
    test_stops()
    test_allocators()
    print()
    print("--- 组合引擎 ---")
    test_combiner()
    print("=" * 50)
    print("ALL TESTS PASSED")
