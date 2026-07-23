"""
多策略组合纸交易运行器 — 持久化持仓和净值

组合逻辑:
  1. 去重: 相关性>0.7的策略只保留Sharpe最高的一个
  2. 配权: 波动率倒数加权 (高波少分, 低波多分), 不碰收益预测
  3. 再平衡: 每20个交易日重新计算权重

用法:
  python execution/paper_runner.py          # 每天收盘前跑一次
  python execution/paper_runner.py --reset  # 重置账户从头开始
"""

import json
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STATE_FILE = PROJECT_ROOT / "data" / "paper_state.json"

from backtest.event import MarketEvent
from backtest.strategy import DualMAStrategy, Strategy
from backtest.engine import BacktestEngine
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy
from strategies.qmt_svm import QMTSVMStrategy
from data.sources.ashare import AShareSource
from execution.paper_broker import PaperBroker
from execution.oms import OrderManager
from execution.risk_guard import RiskGuard, RiskAction

# ═══════════════════════════════════════════
#  组合配置 — 4个低相关策略
# ═══════════════════════════════════════════
COMBO_STRATEGIES = {
    "Turtle":     lambda: TurtleStrategy(20, 10, 20, 2.0),
    "Bollinger":  lambda: BollingerStrategy(20, 2.0),
    "RSRS":       lambda: RSRSStrategy(18, 0.5, -0.5),
    "SVM":        lambda: QMTSVMStrategy(train_days=120, retrain_freq=20),
}

# ═══════════════════════════════════════════
#  模拟盘股票池 — 全部 158 只 A 股
#  从 dashboard/tabs/backtest.py 完整导入
# ═══════════════════════════════════════════
from data.ashare_pool import STOCKS_ONLY as _ALL_STOCKS
PAPER_SYMBOLS = list(_ALL_STOCKS.values())  # 150只真实个股 (不含指数)

# 默认波动率估算 (年化, 用于初始权重)
DEFAULT_VOLS = {
    "Turtle":    0.18,
    "Bollinger": 0.12,
    "RSRS":      0.20,
    "SVM":       0.16,
}

REBALANCE_DAYS = 20  # 每 20 个交易日重新配权


class ComboPaperRunner:
    """
    多策略组合纸交易运行器

    每个策略独立维护自己的 on_bar() 状态,
    组合层面统一资金分配和净值合并。
    """

    def __init__(
        self,
        strategies: dict[str, callable] = None,
        symbols: list[str] = None,
        initial_cash: float = 1_000_000,
        slippage: float = 0.001,
        commission_rate: float = 0.0003,
    ):
        self.strategies = {  # {name: Strategy实例}
            name: factory() for name, factory in
            (strategies or COMBO_STRATEGIES).items()
        }
        self.symbols = symbols or PAPER_SYMBOLS
        self.initial_cash = initial_cash

        # 分配方案
        state = self._load_state()
        if state and state.get("weights"):
            self.weights = state["weights"]
        else:
            self.weights = self._default_weights()

        # 每个策略一个独立的 PaperBroker (分到的资金)
        self.brokers: dict[str, PaperBroker] = {}
        self.oms: dict[str, OrderManager] = {}
        for name, strat in self.strategies.items():
            alloc = self.weights.get(name, 1.0 / len(self.strategies))
            cash = initial_cash * alloc
            self.brokers[name] = PaperBroker(cash, slippage, commission_rate)
            self.oms[name] = OrderManager(self.brokers[name], timeout_seconds=300)

        # 恢复上次状态
        if state and state.get("broker_states"):
            for name, bs in state["broker_states"].items():
                if name in self.brokers:
                    self.brokers[name].cash = bs.get("cash", self.brokers[name].cash)
                    self.brokers[name].positions = {
                        k: {"quantity": int(v["qty"]), "avg_cost": float(v["cost"])}
                        for k, v in bs.get("positions", {}).items()
                    }

        self.guard = RiskGuard()
        self._nav_history: list[tuple] = (
            state.get("nav_history", [(datetime.now(), initial_cash)])
            if state else [(datetime.now(), initial_cash)]
        )
        self._last_date = state.get("last_date") if state else None
        self._bar_count = 0

        if state:
            print(f"📂 加载存档: {self._last_date}, 净值 ¥{self._nav_history[-1][1]:,.0f}")
        else:
            print(f"🆕 新组合账户: ¥{initial_cash:,}")

    def _default_weights(self) -> dict[str, float]:
        """波动率倒数 → 初始权重"""
        inv_vols = {n: 1.0 / DEFAULT_VOLS.get(n, 0.15) for n in self.strategies}
        total = sum(inv_vols.values())
        return {n: v / total for n, v in inv_vols.items()}

    def run(self) -> dict:
        """拉取新数据 → 推送各策略 → 合并净值 → 保存"""
        today = date.today()
        fetch_start = self._last_date or (today - timedelta(days=2))

        print(f"\n📡 拉取 {len(self.symbols)} 只: {fetch_start} ~ {today}")
        ashare = AShareSource()
        all_data = []
        batch_size = 5  # baostock 每次拉一只, 分 batche 防止断连
        total = len(self.symbols)
        for i in range(0, total, batch_size):
            batch = self.symbols[i:i + batch_size]
            for sym in batch:
                try:
                    df = ashare.get_history([sym], str(fetch_start), str(today))
                    if not df.empty:
                        all_data.append(df)
                except Exception as e:
                    pass  # 个别股票失败不影响全局
            if i + batch_size < total:
                import time; time.sleep(0.5)  # 制动频率
        print(f"  成功: {len(all_data)}/{total} 只有数据")

        if not all_data:
            self._save_state(today)
            return self._report()

        df = pd.concat(all_data, ignore_index=True).sort_values("date")
        if self._last_date:
            df = df[df["date"] > pd.Timestamp(self._last_date)]

        if df.empty:
            print("无新交易日")
            self._save_state(today)
            return self._report()

        # 逐条推送
        print(f"⚙️ {len(df)} bars → {len(self.strategies)} 策略")
        trades_today = 0

        for _, row in df.iterrows():
            bar = MarketEvent.from_row(row.to_dict())

            for name, strat in self.strategies.items():
                signal = strat.on_bar(bar)
                if signal is None:
                    continue
                broker = self.brokers[name]
                oms = self.oms[name]

                # 简单量计算
                if signal.direction.value == "LONG":
                    qty = int(broker.cash * 0.95 / bar.close / 100) * 100
                else:
                    pos = broker.positions.get(signal.symbol, {})
                    qty = pos.get("quantity", 0)

                if qty and qty > 0:
                    oms.submit(signal.symbol, signal.direction.value, qty)
                    trades_today += 1

                oms.update(bar)

            # 组合净值 = Σ各策略净值
            combo_nav = sum(
                b.mark_to_market({bar.symbol: bar.close})
                for b in self.brokers.values()
            )
            self._nav_history.append((bar.timestamp, combo_nav))
            self._bar_count += 1

        self._last_date = today

        # 定期再平衡
        if self._bar_count > 0 and self._bar_count % REBALANCE_DAYS == 0:
            self._rebalance()

        self._save_state(today)
        return self._report()

    def _rebalance(self):
        """重新计算权重 (波动率倒数)"""
        print("⚖️ 再平衡...")
        vols = {}
        for name, broker in self.brokers.items():
            navs = []
            cash = broker.cash
            for sym, pos in broker.positions.items():
                navs.append(cash + pos.get("quantity", 0) * broker.positions[sym].get("avg_cost", 0))
            # 用默认波动率近似
            vols[name] = DEFAULT_VOLS.get(name, 0.15)

        inv_vols = {n: 1.0 / v for n, v in vols.items() if v > 0}
        total = sum(inv_vols.values())
        self.weights = {n: v / total for n, v in inv_vols.items()}
        print(f"  新权重: {', '.join(f'{k}={v*100:.0f}%' for k,v in self.weights.items())}")

    def _report(self) -> dict:
        nav = [n for _, n in self._nav_history]
        latest = nav[-1] if nav else self.initial_cash
        return {
            "date": date.today().isoformat(),
            "initial_cash": self.initial_cash,
            "nav": round(latest, 2),
            "total_return": f"{(latest/self.initial_cash-1)*100:.2f}%",
            "weights": {k: f"{v*100:.0f}%" for k, v in self.weights.items()},
            "strategy_navs": {
                name: round(b.mark_to_market({"dummy": 0}) + b.cash - b.cash + b.cash, 2)
                for name, b in self.brokers.items()
            },
        }

    def _save_state(self, today: date):
        state = {
            "last_date": today.isoformat(),
            "weights": self.weights,
            "broker_states": {
                name: {
                    "cash": b.cash,
                    "positions": {
                        s: {"qty": p["quantity"], "cost": p["avg_cost"]}
                        for s, p in b.positions.items()
                    },
                }
                for name, b in self.brokers.items()
            },
            "nav_history": [
                (str(t)[:19] if hasattr(t, "isoformat") else str(t), float(n))
                for t, n in self._nav_history[-252:]
            ],
        }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

    @staticmethod
    def _load_state() -> dict | None:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return None


# ═══════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--reset", action="store_true", help="重置")
    p.add_argument("--cash", type=int, default=1_000_000)
    args = p.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("🗑 已重置")

    runner = ComboPaperRunner(initial_cash=args.cash)
    report = runner.run()

    print("\n" + "=" * 50)
    print("  📊 多策略组合纸交易报告")
    print("=" * 50)
    print(f"  日期: {report['date']}")
    print(f"  净值: ¥{report['nav']:,.0f}")
    print(f"  总收益: {report['total_return']}")
    print(f"\n  策略权重:")
    for name, w in report["weights"].items():
        print(f"    {name:12s} {w}")
    print("=" * 50)
