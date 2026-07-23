"""
纸交易引擎 v3 — 并行独立策略 + 自定义组合

PART 1: 每个策略拿全部初始资金独立运行，展示各自持仓/收益/买卖/指标
PART 2: 自定义策略组合，自由选策略+配权重，按组合权重分配资金

用法:
  runner = IndividualRunner(symbols, cash=1_000_000)
  report = runner.run()  # 返回 {策略名: 运行报告}
"""

import json
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.sources.ashare import AShareSource
from data.ashare_pool import STOCKS_ONLY
from backtest.event import MarketEvent
from backtest.strategy import DualMAStrategy, BuyAndHoldStrategy, Strategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy
from strategies.qmt_svm import QMTSVMStrategy
from strategies.qmt_arima import QMTARIMAStrategy
from strategies.qmt_index_ma import QMTIndexMAStrategy
from strategies.multifactor import MultiFactorStrategy
from strategies.pairs import PairsStrategy
from execution.paper_broker import PaperBroker
from execution.oms import OrderManager

STATE_FILE = PROJECT_ROOT / "data" / "paper_state.json"
STATE_FILE_INDIVIDUAL = PROJECT_ROOT / "data" / "paper_individual.json"
STATE_FILE_COMBO = PROJECT_ROOT / "data" / "paper_combo.json"

# ═══════════════════════════════════════════
#  全部 10 个策略
# ═══════════════════════════════════════════
ALL_STRATEGIES = {
    "Buy&Hold":   lambda: BuyAndHoldStrategy(),
    "DualMA":     lambda: DualMAStrategy(5, 20),
    "Bollinger":  lambda: BollingerStrategy(20, 2.0),
    "Turtle":     lambda: TurtleStrategy(20, 10, 20, 2.0),
    "RSRS":       lambda: RSRSStrategy(18, 0.5, -0.5),
    "MultiFactor": lambda: MultiFactorStrategy(top_k=5),
    "Pairs":      lambda: PairsStrategy(60, 2.0, 0.0),
    "SVM":        lambda: QMTSVMStrategy(train_days=120, retrain_freq=20),
    "ARIMA":      lambda: QMTARIMAStrategy(history=120, refit_freq=5),
    "IndexMA":    lambda: QMTIndexMAStrategy("上证50", 5, 20),
}

STRATEGY_VOLS = {
    "Buy&Hold": 0.14, "DualMA": 0.16, "Bollinger": 0.12,
    "Turtle": 0.18, "RSRS": 0.20, "MultiFactor": 0.15,
    "Pairs": 0.13, "SVM": 0.16, "ARIMA": 0.17, "IndexMA": 0.16,
}

PAPER_SYMBOLS = list(STOCKS_ONLY.values())


@dataclass
class StrategyReport:
    """单个策略的运行报告"""
    name: str = ""
    cash: float = 0
    nav: float = 0
    total_return: str = "0.00%"
    positions: dict = field(default_factory=dict)  # {symbol: {qty, avg_cost}}
    buys: list = field(default_factory=list)       # [{date, symbol, qty, price}]
    sells: list = field(default_factory=list)      # [{date, symbol, qty, price}]
    nav_history: list = field(default_factory=list)
    trade_count: int = 0
    win_rate: str = "—"
    sharpe: float = 0.0
    mdd: str = "0.00%"


class IndividualRunner:
    """PART 1: 每个策略独立拿全部资金运行"""

    def __init__(self, symbols: list[str] = None, initial_cash: float = 1_000_000):
        self.symbols = symbols or PAPER_SYMBOLS
        self.cash = initial_cash
        self.strategies = {name: factory() for name, factory in ALL_STRATEGIES.items()}
        self.brokers: dict[str, PaperBroker] = {}
        self.oms: dict[str, OrderManager] = {}
        self.reports: dict[str, StrategyReport] = {}
        self._nav_histories: dict[str, list] = defaultdict(list)
        self._buys: dict[str, list] = defaultdict(list)
        self._sells: dict[str, list] = defaultdict(list)

        for name in self.strategies:
            self.brokers[name] = PaperBroker(self.cash, 0.001, 0.0003)
            self.oms[name] = OrderManager(self.brokers[name], timeout_seconds=300)

    def run(self, start_date: str = "2026-01-01", end_date: str = None) -> dict[str, StrategyReport]:
        """拉数据 → 每个策略独立运行 → 返回所有报告"""
        if end_date is None:
            end_date = (date.today() - timedelta(days=1)).isoformat()

        print(f"📡 拉取 {len(self.symbols)} 只股票 {start_date}~{end_date} ...")
        ashare = AShareSource()
        all_data = []
        for i, sym in enumerate(self.symbols):
            try:
                df = ashare.get_history([sym], start_date, end_date)
                if not df.empty:
                    all_data.append(df)
            except Exception:
                pass
            if (i + 1) % 30 == 0:
                print(f"  {i+1}/{len(self.symbols)} ...")
        if not all_data:
            return {}

        df = pd.concat(all_data, ignore_index=True).sort_values("date")
        n_symbols = df["symbol"].nunique()
        print(f"  数据: {len(df)} rows, {n_symbols} symbols")

        # 每个策略独立逐条推送
        print(f"\n⚙️ 运行 {len(self.strategies)} 个策略...")
        for s_idx, (name, strat) in enumerate(self.strategies.items()):
            broker = self.brokers[name]
            oms = self.oms[name]
            for _, row in df.iterrows():
                bar = MarketEvent.from_row(row.to_dict())
                signal = strat.on_bar(bar)
                if signal is not None:
                    if signal.direction.value == "LONG":
                        qty = int(broker.cash * 0.95 / bar.close / 100) * 100
                        if qty and qty > 0:
                            oms.submit(signal.symbol, "LONG", qty)
                            self._buys[name].append({
                                "date": str(row["date"])[:10], "symbol": signal.symbol,
                                "qty": qty, "price": round(bar.close, 2),
                            })
                    else:
                        pos = broker.positions.get(signal.symbol, {})
                        qty = pos.get("quantity", 0)
                        if qty and qty > 0:
                            oms.submit(signal.symbol, "EXIT", qty)
                            self._sells[name].append({
                                "date": str(row["date"])[:10], "symbol": signal.symbol,
                                "qty": qty, "price": round(bar.close, 2),
                            })
                oms.update(bar)
                nav = broker.mark_to_market({bar.symbol: bar.close})
                self._nav_histories[name].append((bar.timestamp, nav))

            pos_count = len(broker.positions)
            pos_value = sum(p["quantity"] * (p["avg_cost"] or bar.close)
                          for p in broker.positions.values())
            final_nav = broker.cash + pos_value

            # 计算指标
            navs = [n for _, n in self._nav_histories[name]]
            if len(navs) >= 2:
                rets = np.diff(navs) / navs[:-1]
                vol = float(np.std(rets, ddof=1) * np.sqrt(252))
                sharpe = float((np.mean(rets) * 252 - 0.025) / vol) if vol > 0 else 0
                running_max = np.maximum.accumulate(navs)
                dd = float(np.min((navs - running_max) / running_max))
                total_trades = len(self._buys[name]) + len(self._sells[name])
                wins = sum(1 for s in self._sells[name]
                          if s["price"] > (self._buys[name][i]["price"] if i < len(self._buys[name]) else s["price"]))
                win_rate = f"{wins/max(total_trades,1)*100:.0f}%" if total_trades > 0 else "—"
            else:
                vol, sharpe, dd, total_trades, win_rate = 0, 0, 0, 0, "—"

            self.reports[name] = StrategyReport(
                name=name, cash=broker.cash, nav=final_nav,
                total_return=f"{(final_nav/self.cash-1)*100:.2f}%",
                positions={s: {"qty": p["quantity"], "avg_cost": round(p["avg_cost"],2)}
                          for s, p in broker.positions.items()},
                buys=self._buys[name][-20:], sells=self._sells[name][-20:],
                nav_history=self._nav_histories[name][-252:],
                trade_count=total_trades, win_rate=win_rate,
                sharpe=round(sharpe, 3), mdd=f"{dd*100:.2f}%",
            )

            print(f"  {name:12s} NAV=¥{final_nav:,.0f} ({self.reports[name].total_return}) "
                  f"持仓{pos_count}只 交易{total_trades}次")

        self._save(df["date"].max())
        return self.reports

    def _save(self, last_date):
        state = {
            "last_date": str(last_date)[:10], "cash": self.cash,
            "reports": {name: {
                "nav": r.nav, "total_return": r.total_return,
                "positions": r.positions, "trade_count": r.trade_count,
                "sharpe": r.sharpe, "mdd": r.mdd, "win_rate": r.win_rate,
                "buys": r.buys[-20:], "sells": r.sells[-20:],
                "nav_history": [
                    (str(t)[:19] if hasattr(t, "isoformat") else str(t), float(n))
                    for t, n in r.nav_history[-252:]
                ],
            } for name, r in self.reports.items()},
        }
        STATE_FILE_INDIVIDUAL.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE_INDIVIDUAL, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

    @staticmethod
    def load_state() -> dict | None:
        if STATE_FILE_INDIVIDUAL.exists():
            with open(STATE_FILE_INDIVIDUAL, "r", encoding="utf-8") as f:
                return json.load(f)
        return None


class ComboRunner:
    """PART 2: 自定义策略组合"""

    def __init__(self, strategy_weights: dict[str, float], symbols=None, cash=1_000_000):
        self.weights = strategy_weights
        self.cash = cash
        self.symbols = symbols or PAPER_SYMBOLS
        self.strategies = {name: ALL_STRATEGIES[name]() for name in strategy_weights}
        self.brokers = {name: PaperBroker(cash * w, 0.001, 0.0003)
                       for name, w in strategy_weights.items()}
        self.oms = {name: OrderManager(self.brokers[name], timeout_seconds=300)
                   for name in strategy_weights}
        self._nav_history: list[tuple] = []
        self._buys: list[dict] = []
        self._sells: list[dict] = []

    def run(self, start_date="2026-01-01", end_date=None) -> StrategyReport:
        if end_date is None:
            end_date = (date.today() - timedelta(days=1)).isoformat()

        ashare = AShareSource()
        all_data = []
        for sym in self.symbols:
            try:
                df = ashare.get_history([sym], start_date, end_date)
                if not df.empty:
                    all_data.append(df)
            except Exception:
                pass
        if not all_data:
            return StrategyReport(name="Combo")

        df = pd.concat(all_data, ignore_index=True).sort_values("date")

        for _, row in df.iterrows():
            bar = MarketEvent.from_row(row.to_dict())
            for name, strat in self.strategies.items():
                signal = strat.on_bar(bar)
                if signal is None:
                    continue
                broker = self.brokers[name]
                oms = self.oms[name]
                if signal.direction.value == "LONG":
                    qty = int(broker.cash * 0.95 / bar.close / 100) * 100
                    if qty and qty > 0:
                        oms.submit(signal.symbol, "LONG", qty)
                        self._buys.append({"date": str(row["date"])[:10],
                                           "strategy": name, "symbol": signal.symbol,
                                           "qty": qty, "price": round(bar.close, 2)})
                else:
                    pos = broker.positions.get(signal.symbol, {})
                    qty = pos.get("quantity", 0)
                    if qty and qty > 0:
                        oms.submit(signal.symbol, "EXIT", qty)
                        self._sells.append({"date": str(row["date"])[:10],
                                            "strategy": name, "symbol": signal.symbol,
                                            "qty": qty, "price": round(bar.close, 2)})
                oms.update(bar)
            combo_nav = sum(b.mark_to_market({bar.symbol: bar.close})
                          for b in self.brokers.values())
            self._nav_history.append((bar.timestamp, combo_nav))

        all_positions = {}
        for name, broker in self.brokers.items():
            for sym, p in broker.positions.items():
                all_positions[f"{name}/{sym}"] = {"qty": p["quantity"],
                                                   "avg_cost": round(p["avg_cost"], 2)}

        final_nav = sum(b.mark_to_market({"dummy": 0}) - b.mark_to_market({"dummy": 0}) + b.cash +
                        sum(p["quantity"] * (p["avg_cost"] or 0) for p in b.positions.values())
                        for b in self.brokers.values())  # simplified
        final_nav = sum(b.cash + sum(p["quantity"] * (p.get("avg_cost", 0) or 0)
                       for p in b.positions.values()) for b in self.brokers.values())

        navs = [n for _, n in self._nav_history]
        if len(navs) >= 2:
            rets = np.diff(navs) / navs[:-1]
            vol = float(np.std(rets, ddof=1) * np.sqrt(252))
            sharpe = float((np.mean(rets) * 252 - 0.025) / vol) if vol > 0 else 0
            running_max = np.maximum.accumulate(navs)
            dd = float(np.min((navs - running_max) / running_max))
        else:
            vol, sharpe, dd = 0, 0, 0

        return StrategyReport(
            name="Combo", nav=final_nav,
            total_return=f"{(final_nav/self.cash-1)*100:.2f}%",
            positions=all_positions, buys=self._buys[-20:], sells=self._sells[-20:],
            nav_history=self._nav_history[-252:],
            trade_count=len(self._buys) + len(self._sells),
            sharpe=round(sharpe, 3), mdd=f"{dd*100:.2f}%",
        )


# ═══════════════════════════════════════════
#  种子: 预设所有策略的运行结果
# ═══════════════════════════════════════════
def seed_all(cash=1_000_000):
    """一次性跑所有策略,生成种子数据存盘"""
    print("=" * 60)
    print("  PART 1: 独立策略 (每个 ¥{:,})".format(cash))
    print("=" * 60)
    runner = IndividualRunner(initial_cash=cash)
    reports = runner.run()
    print("\n✓ Individual state saved")
    return reports
