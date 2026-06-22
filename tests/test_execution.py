"""执行层测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from execution.paper_broker import PaperBroker
from execution.oms import OrderManager, OrderStatus
from execution.risk_guard import RiskGuard, RiskAction
from execution.paper_engine import PaperTradingEngine
from backtest.strategy import BuyAndHoldStrategy, DualMAStrategy
from backtest.engine import BacktestEngine


def _make_bar(symbol="TEST", close=100, timestamp=None):
    from backtest.event import MarketEvent
    return MarketEvent(
        timestamp=timestamp or pd.Timestamp("2024-06-15"),
        symbol=symbol, open=close*0.99, high=close*1.02,
        low=close*0.98, close=close, volume=1e8,
    )


def test_paper_broker():
    """PaperBroker 模拟下单→成交"""
    broker = PaperBroker(1_000_000, slippage=0.001, commission_rate=0.0003)
    bar = _make_bar(close=100)

    # 市价买入
    oid = broker.submit_order("TEST", "LONG", 1000)
    fills = broker.try_execute_pending(bar)
    assert len(fills) == 1
    status = broker.get_order_status(oid)
    assert status["status"] == OrderStatus.FILLED

    # 持仓检查
    pos = broker.get_positions()
    assert "TEST" in pos
    assert pos["TEST"]["quantity"] == 1000

    # 卖出
    oid2 = broker.submit_order("TEST", "EXIT", 1000)
    fills2 = broker.try_execute_pending(bar)
    assert len(fills2) == 1
    assert "TEST" not in broker.get_positions()
    print(f"✓ PaperBroker: 买→卖, cash={broker.cash:,.0f} (应略低于初始，含滑点+手续费)")


def test_oms_timeout():
    """OMS 超时撤单"""
    broker = PaperBroker(1_000_000)
    oms = OrderManager(broker, timeout_seconds=0, max_retries=0)  # 立即超时
    oms.submit("TEST", "LONG", 1000)
    bar = _make_bar(close=100)
    fills = oms.update(bar)  # 立即成交 (PaperBroker 市价单不等待)
    # 因为 timeout_seconds=0 但单子已经成交了，所以 pending 为 0
    assert oms.active_count == 0
    print(f"✓ OMS: 订单立即成交, active={oms.active_count}")


def test_risk_guard():
    """风控规则"""
    guard = RiskGuard(max_daily_loss=0.05, max_drawdown=0.20)
    guard.initialize(1_000_000, 1_000_000, pd.Timestamp("2024-06-15").date())

    # 正常
    action, _ = guard.check(1_010_000, {}, pd.Timestamp("2024-06-15").date())
    assert action == RiskAction.ALLOW

    # 日亏损 6% → BLOCK
    action, reason = guard.check(940_000, {}, pd.Timestamp("2024-06-15").date())
    assert action == RiskAction.BLOCK_BUY, f"Got {action}: {reason}"
    print(f"✓ RiskGuard: 日亏6% → {action.value}")

    # 最大回撤 21% → LIQUIDATE
    guard2 = RiskGuard(max_daily_loss=0.50, max_drawdown=0.20)
    guard2.initialize(1_000_000, 1_200_000, pd.Timestamp("2024-01-01").date())
    guard2.check(1_190_000, {}, pd.Timestamp("2024-01-05").date())  # 峰值 1.2M
    action, _ = guard2.check(940_000, {}, pd.Timestamp("2024-01-10").date())
    assert action == RiskAction.LIQUIDATE_ALL, f"Got {action}"
    print(f"✓ RiskGuard: 回撤21% → {action.value}")


def test_paper_vs_backtest():
    """纸交易引擎 vs 回测引擎 差异对比"""
    # 生成测试数据
    dates = pd.date_range("2024-01-02", periods=100, freq="B")
    np.random.seed(42)
    rets = np.random.normal(0.0002, 0.01, 100)
    close = 100 * np.exp(np.cumsum(rets))
    df = pd.DataFrame({
        "symbol": "TEST", "date": dates,
        "open": close*0.99, "high": close*1.02, "low": close*0.98,
        "close": close, "volume": 1e8, "amount": close*1e8,
        "market": "test", "interval": "daily",
    })

    # 回测引擎 (立即成交)
    eng_bt = BacktestEngine(df, BuyAndHoldStrategy(), 1_000_000, slippage=0.001, commission_rate=0.0003)
    r_bt = eng_bt.run()

    # 纸交易引擎 (走 PaperBroker+OMS)
    eng_paper = PaperTradingEngine(BuyAndHoldStrategy(), ["TEST"], 1_000_000, slippage=0.001, commission_rate=0.0003)
    r_paper = eng_paper.replay_from_store(df)

    diff = abs(r_bt.total_return - r_paper.total_return)
    print(f"  Backtest: {r_bt.total_return*100:.3f}%")
    print(f"  Paper:    {r_paper.total_return*100:.3f}%")
    print(f"  Difference: {diff*100:.4f}% (应 < 1%)")
    assert diff < 0.01, f"差异过大: {diff:.4%}"
    print("✓ 纸交易 vs 回测 差异在合理范围")


if __name__ == "__main__":
    print("=" * 50)
    test_paper_broker()
    test_oms_timeout()
    test_risk_guard()
    print()
    print("--- 纸交易 vs 回测 ---")
    test_paper_vs_backtest()
    print("=" * 50)
    print("ALL TESTS PASSED")
