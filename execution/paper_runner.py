"""
纸交易引擎 v4 — 缓存加速 + 基准对比 + 历史记录 + 增量更新

缓存: CachedFetcher → SQLite → 第二次跑 100x 快
基准: 自动拉取沪深300做对比
历史: 每次运行保存独立时间戳快照到 paper_history/
"""
import json
import sys
import os
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.cache import CachedFetcher
from data.ashare_pool import get_code_list
from data.store import DataStore
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

STATE_FILE_INDIVIDUAL = PROJECT_ROOT / "data" / "paper_individual.json"
STATE_FILE_COMBO = PROJECT_ROOT / "data" / "paper_combo.json"
HISTORY_DIR = PROJECT_ROOT / "data" / "paper_history"

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

_CACHE_SYMS: list[str] | None = None


def _get_symbols() -> list[str]:
    global _CACHE_SYMS
    if _CACHE_SYMS is None:
        _CACHE_SYMS = get_code_list()
    return _CACHE_SYMS


@dataclass
class StrategyReport:
    name: str = ""
    cash: float = 0
    nav: float = 0
    total_return: str = "0.00%"
    positions: dict = field(default_factory=dict)
    buys: list = field(default_factory=list)
    sells: list = field(default_factory=list)
    nav_history: list = field(default_factory=list)
    bench_history: list = field(default_factory=list)
    trade_count: int = 0
    win_rate: str = "—"
    sharpe: float = 0.0
    mdd: str = "0.00%"
    bench_return: str = "0.00%"


class IndividualRunner:
    """PART 1: 每个策略独立拿全部资金运行"""

    def __init__(self, symbols=None, initial_cash=1_000_000):
        self.symbols = symbols or _get_symbols()
        self.cash = initial_cash
        self.strategies = {name: factory() for name, factory in ALL_STRATEGIES.items()}
        self.brokers = {n: PaperBroker(initial_cash, 0.001, 0.0003) for n in self.strategies}
        self.oms = {n: OrderManager(self.brokers[n], 300) for n in self.strategies}
        self.reports: dict[str, StrategyReport] = {}
        self._navs: dict[str, list] = {n: [] for n in self.strategies}
        self._buys: dict[str, list] = {n: [] for n in self.strategies}
        self._sells: dict[str, list] = {n: [] for n in self.strategies}
        self._bench_history: list[tuple] = []

    def run(self, start="2026-01-01", end=None):
        if end is None:
            end = (date.today() - timedelta(days=1)).isoformat()

        cache = CachedFetcher()
        df = cache.get(self.symbols, start, end)
        if df.empty:
            return {}
        n_symbols = df["symbol"].nunique()

        # 拉基准
        try:
            df_bench = cache.get(["sh.000300"], start, end)
            bench_close = dict(zip(df_bench["date"], df_bench["close"]))
        except Exception:
            bench_close = {}

        print(f"📡 {n_symbols} symbols × {len(self.strategies)} strategies (cached)")

        for name, strat in self.strategies.items():
            broker = self.brokers[name]
            oms = self.oms[name]
            for _, row in df.iterrows():
                bar = MarketEvent.from_row(row.to_dict())
                signal = strat.on_bar(bar)
                if signal is not None:
                    d = signal.direction.value
                    qty = int(broker.cash * 0.95 / bar.close / 100) * 100 if d == "LONG" else broker.positions.get(signal.symbol, {}).get("quantity", 0)
                    if qty and qty > 0:
                        oms.submit(signal.symbol, d, qty)
                        (self._buys[name] if d == "LONG" else self._sells[name]).append(
                            {"date": str(row["date"])[:10], "symbol": signal.symbol,
                             "qty": qty, "price": round(bar.close, 2)})
                oms.update(bar)
                self._navs[name].append((bar.timestamp, broker.mark_to_market({bar.symbol: bar.close})))

            pos_count = len(broker.positions)
            pos_value = sum(p["quantity"] * (p["avg_cost"] or 0) for p in broker.positions.values())
            final_nav = broker.cash + pos_value
            navs = [n for _, n in self._navs[name]]
            rets = np.diff(navs) / navs[:-1] if len(navs) >= 2 else np.array([])
            vol = float(np.std(rets, ddof=1) * np.sqrt(252)) if len(rets) > 0 else 0
            sharpe = float((np.mean(rets) * 252 - 0.025) / vol) if vol > 0 else 0
            running_max = np.maximum.accumulate(navs)
            dd = float(np.min((navs - running_max) / running_max)) if len(navs) > 1 else 0
            total_trades = len(self._buys[name]) + len(self._sells[name])

            bench_ret = "—"
            if bench_close and self._navs[name]:
                first_d = self._navs[name][0][0]
                last_d = self._navs[name][-1][0]
                b_first = bench_close.get(first_d, bench_close.get(min(bench_close.keys()) if bench_close else 0, 0))
                b_last = bench_close.get(last_d, b_last := (list(bench_close.values())[-1] if bench_close else 0))
                if b_first and b_first > 0:
                    bench_ret = f"{(b_last/b_first-1)*100:.2f}%"

            self.reports[name] = StrategyReport(
                name=name, cash=broker.cash, nav=final_nav,
                total_return=f"{(final_nav/self.cash-1)*100:.2f}%",
                positions={s: {"qty": p["quantity"], "avg_cost": round(p["avg_cost"], 2)}
                          for s, p in broker.positions.items()},
                buys=self._buys[name][-20:], sells=self._sells[name][-20:],
                nav_history=self._navs[name][-252:],
                trade_count=total_trades, sharpe=round(sharpe, 3), mdd=f"{dd*100:.2f}%",
                bench_return=bench_ret,
            )
            print(f"  {name:12s} NAV=¥{final_nav:,.0f} ({self.reports[name].total_return}) "
                  f"vs 沪深300 {bench_ret} 持仓{pos_count}只")

        self._save(df["date"].max(), df_bench)
        return self.reports

    def _save(self, last_date, df_bench=None):
        last_str = str(last_date)[:10]
        state = {
            "last_date": last_str, "cash": self.cash,
            "reports": {n: {
                "nav": r.nav, "total_return": r.total_return,
                "positions": r.positions, "trade_count": r.trade_count,
                "sharpe": r.sharpe, "mdd": r.mdd, "win_rate": r.win_rate,
                "bench_return": r.bench_return,
                "buys": r.buys, "sells": r.sells,
                "nav_history": [(str(t)[:19], float(n)) for t, n in r.nav_history[-252:]],
            } for n, r in self.reports.items()},
        }
        STATE_FILE_INDIVIDUAL.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE_INDIVIDUAL, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

        # 历史快照
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        snap = {**state, "timestamp": datetime.now().isoformat()}
        snap_path = HISTORY_DIR / f"paper_{last_str}.json"
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2, default=str)

    @staticmethod
    def load_state():
        if STATE_FILE_INDIVIDUAL.exists():
            with open(STATE_FILE_INDIVIDUAL, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    @staticmethod
    def load_history():
        """返回所有历史快照"""
        if not HISTORY_DIR.exists():
            return []
        snaps = []
        for fp in sorted(HISTORY_DIR.glob("paper_*.json")):
            with open(fp, "r", encoding="utf-8") as f:
                snaps.append(json.load(f))
        return snaps


def seed_all(cash=1_000_000):
    """一次性跑所有策略, 生成种子数据"""
    print("=" * 60)
    print(f"  PART 1: 独立策略 (每个 ¥{cash:,}, 全市场股票)")
    print("=" * 60)
    runner = IndividualRunner(initial_cash=cash)
    return runner.run()
