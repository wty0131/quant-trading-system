"""
回测引擎测试

验证：买入持有策略的回测结果应与手动计算一致
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from backtest.engine import BacktestEngine
from backtest.strategy import BuyAndHoldStrategy, DualMAStrategy
from backtest.event import MarketEvent, Direction
from backtest.portfolio import Portfolio
from backtest.execution import ExecutionHandler
from backtest.analytics import generate_report, BacktestReport


def _get_test_data() -> pd.DataFrame:
    """生成已知结果的测试数据"""
    dates = pd.date_range("2024-01-02", periods=100, freq="B")
    np.random.seed(42)
    returns = np.random.normal(0.0002, 0.01, 100)
    close = 100 * np.exp(np.cumsum(returns))

    return pd.DataFrame({
        "symbol": "TEST",
        "date": dates,
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": 1e8,
        "amount": close * 1e8,
        "market": "test",
        "interval": "daily",
    })


def test_buy_and_hold():
    """买入持有策略：回测结果应接近手动计算"""
    df = _get_test_data()

    engine = BacktestEngine(
        df=df,
        strategy=BuyAndHoldStrategy(),
        initial_cash=1_000_000,
        slippage=0.0,       # 零滑点，方便验证
        commission_rate=0.0, # 零手续费
    )
    report = engine.run()

    # 手动计算
    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    manual_return = (last_close / first_close) - 1

    print(f"Manual return:  {manual_return*100:.4f}%")
    print(f"Engine return:  {report.total_return*100:.4f}%")

    # 误差应在 0.05% 以内（零滑点零手续费应极接近）
    diff = abs(report.total_return - manual_return)
    assert diff < 0.0005, f"差异过大: {diff:.6f}"
    assert report.total_trades > 0, "应有交易记录"
    assert report.final_nav > 0, "净值应大于0"
    print("✓ Buy & Hold: 回测与手动计算一致")


def test_buy_and_hold_with_commission():
    """带手续费的买入持有：应略低于手动计算"""
    df = _get_test_data()

    engine = BacktestEngine(
        df=df,
        strategy=BuyAndHoldStrategy(),
        initial_cash=1_000_000,
        slippage=0.001,         # 0.1% 滑点
        commission_rate=0.0003, # 万三 手续费
    )
    report = engine.run()

    first_close = df["close"].iloc[0]
    last_close = df["close"].iloc[-1]
    manual_return = (last_close / first_close) - 1

    print(f"Manual return:  {manual_return*100:.4f}%")
    print(f"Engine (cost):  {report.total_return*100:.4f}%")

    # 带摩擦的应低于手动
    assert report.total_return < manual_return, "有摩擦的收益应该低于无摩擦"
    print("✓ Buy & Hold + Cost: 摩擦生效，收益低于裸手动计算")


def test_dual_ma():
    """双均线策略：应产生多次交易"""
    df = _get_test_data()

    engine = BacktestEngine(
        df=df,
        strategy=DualMAStrategy(short=5, long=20),
        initial_cash=1_000_000,
        slippage=0.001,
        commission_rate=0.0003,
    )
    report = engine.run()

    print(f"Trades: {report.total_trades}")
    print(f"Return: {report.total_return*100:.2f}%")
    print(f"MDD:    {report.max_drawdown*100:.2f}%")

    # 应产生至少 1 次交易
    assert report.total_trades >= 1
    # Sharpe 应可计算
    assert -10 < report.sharpe_ratio < 10, "Sharpe 应在合理范围"
    print("✓ Dual MA: 策略正常产生交易信号")


def test_portfolio():
    """测试 Portfolio 的基本操作"""
    pf = Portfolio(initial_cash=1_000_000)

    # 无持仓时净值 = 现金
    pf.mark_to_market(pd.Timestamp("2024-01-02"), {"TEST": 100})
    assert pf.current_nav() == 1_000_000

    # 模拟买入
    from backtest.event import SignalEvent
    signal = SignalEvent(
        timestamp=pd.Timestamp("2024-01-02"),
        symbol="TEST",
        direction=Direction.LONG,
    )
    order = pf.generate_order(signal, 100.0)
    assert order is not None
    assert order.quantity > 0

    # 模拟成交
    from backtest.event import FillEvent
    fill = FillEvent(
        timestamp=pd.Timestamp("2024-01-02"),
        symbol="TEST",
        direction=Direction.LONG,
        quantity=order.quantity,
        price=100.0,
        commission=0.0,
    )
    pf.update(fill)

    # 价格不变，净值应该接近（扣除押金逻辑）或相同
    pf.mark_to_market(pd.Timestamp("2024-01-02"), {"TEST": 100})
    # 买入花了钱但持仓值钱，净值 = 现金 + 持仓市值
    expected = pf.cash + pf.positions["TEST"] * 100
    assert abs(pf.current_nav() - expected) < 0.01

    print(f"Portfolio: cash={pf.cash:,.0f}, positions={pf.positions}, nav={pf.current_nav():,.0f}")
    print("✓ Portfolio: 买卖操作正确")


def test_report():
    """测试报告生成"""
    nav = [(pd.Timestamp("2024-01-02"), 1_000_000),
           (pd.Timestamp("2024-01-03"), 1_010_000),
           (pd.Timestamp("2024-01-04"), 1_005_000)]

    trades = [
        {"timestamp": pd.Timestamp("2024-01-02"), "symbol": "T", "direction": "LONG",
         "price": 100, "quantity": 100, "commission": 0},
        {"timestamp": pd.Timestamp("2024-01-04"), "symbol": "T", "direction": "EXIT",
         "price": 105, "quantity": 100, "commission": 0},
    ]

    report = generate_report(nav, trades, 1_000_000)
    # 最终净值 1_005_000 / 1_000_000 - 1 = 0.005
    assert abs(report.total_return - 0.005) < 0.001
    assert report.total_trades == 2
    assert report.win_rate > 0
    print(f"Report: {report}")
    print("✓ Report: 指标计算正确")


if __name__ == "__main__":
    print("=" * 50)
    test_buy_and_hold()
    print()
    test_buy_and_hold_with_commission()
    print()
    test_dual_ma()
    print()
    test_portfolio()
    print()
    test_report()
    print("=" * 50)
    print("ALL TESTS PASSED")
