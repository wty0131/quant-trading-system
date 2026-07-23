"""
每日纸交易运行器 — 持久化持仓和净值

用法:
  python execution/paper_runner.py          # 每天收盘前跑一次
  python execution/paper_runner.py --reset  # 重置账户从头开始

流程:
  1. 读取上次保存的状态 (paper_state.json)
  2. 从 baostock 拉取上次运行日期到今天的所有新日线
  3. 逐条推送给 Strategy.on_bar() → PaperBroker → OMS → 更新持仓
  4. 保存新状态 + 打印今日报告
"""

import json
import sys
import os
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STATE_FILE = PROJECT_ROOT / "data" / "paper_state.json"

from backtest.event import MarketEvent
from backtest.strategy import DualMAStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy
from data.sources.ashare import AShareSource
from execution.paper_broker import PaperBroker
from execution.oms import OrderManager
from execution.risk_guard import RiskGuard, RiskAction


class DailyPaperRunner:
    """
    每日纸交易运行器

    每次运行时处理从上次运行日期到今天的新 K 线。
    持仓、现金、净值历史跨天持久化到 paper_state.json。
    """

    def __init__(
        self,
        strategy,
        symbols: list[str],
        initial_cash: float = 1_000_000,
        slippage: float = 0.001,
        commission_rate: float = 0.0003,
    ):
        self.strategy = strategy
        self.symbols = symbols
        self.initial_cash = initial_cash

        # 尝试加载上次状态
        state = self._load_state()

        if state:
            self.broker = PaperBroker(
                initial_cash=initial_cash,
                slippage=slippage,
                commission_rate=commission_rate,
            )
            self.broker.cash = state["cash"]
            self.broker.positions = state["positions"]
            self.broker.trade_history = state.get("trades", [])
            self._nav_history = state.get("nav_history", [])
            self._last_date = (
                date.fromisoformat(state["last_date"])
                if state.get("last_date") else None
            )
            print(f"📂 加载上次存档: {self._last_date or '无'}, "
                  f"现金 ¥{self.broker.cash:,.0f}, "
                  f"持仓 {len(self.broker.positions)} 只")
        else:
            self.broker = PaperBroker(
                initial_cash=initial_cash,
                slippage=slippage,
                commission_rate=commission_rate,
            )
            self._nav_history = [(datetime.now(), initial_cash)]
            self._last_date = None
            print(f"🆕 新纸交易账户: 初始资金 ¥{initial_cash:,}")

        self.oms = OrderManager(self.broker, timeout_seconds=300)
        self.guard = RiskGuard()
        self._trade_count_today = 0

    def run(self) -> dict:
        """拉取新数据 → 推送给策略 → 更新持仓 → 保存 → 返回报告"""
        today = date.today()

        # 从上次日期开始拉数据
        fetch_start = self._last_date or today - timedelta(days=2)
        fetch_end = today.isoformat()

        print(f"\n📡 拉取数据: {fetch_start.isoformat()} ~ {fetch_end} ...")
        ashare = AShareSource()
        all_data = []
        for sym in self.symbols:
            try:
                df = ashare.get_history(
                    [sym], fetch_start.isoformat(), fetch_end
                )
                if not df.empty:
                    all_data.append(df)
            except Exception as e:
                print(f"  ⚠ {sym}: {e}")

        if not all_data:
            print("无新数据，无需处理")
            self._save_state(today)
            return self._report()

        df = pd.concat(all_data, ignore_index=True).sort_values("date")
        print(f"  获取 {len(df)} 条新数据 ({df['symbol'].nunique()} 只)")

        # 只处理上次日期之后的新 bar
        if self._last_date:
            df = df[df["date"] > pd.Timestamp(self._last_date)]

        if df.empty:
            print("上次运行后无新交易日")
            self._save_state(today)
            return self._report()

        # 逐条推送
        print(f"\n⚙️ 处理 {len(df)} 根 K 线...")
        for _, row in df.iterrows():
            bar = MarketEvent.from_row(row.to_dict())

            # 风控
            bar_date = bar.timestamp.date()
            current_nav = self._current_nav(bar.close)
            action, reason = self.guard.check(
                current_nav,
                positions=self._position_values(bar),
                today=bar_date,
            )

            # 策略
            signal = self.strategy.on_bar(bar)

            if signal is not None and action == RiskAction.ALLOW:
                qty = self._calc_qty(signal, bar)
                if qty and qty > 0:
                    self.oms.submit(
                        symbol=signal.symbol,
                        direction=signal.direction.value,
                        quantity=qty,
                    )
                    self._trade_count_today += 1
            elif action == RiskAction.LIQUIDATE_ALL:
                self._liquidate_all(bar)
            elif action == RiskAction.BLOCK_BUY and signal is not None:
                if signal.direction.value == "EXIT":
                    qty = self._calc_qty(signal, bar)
                    if qty:
                        self.oms.submit(signal.symbol, "EXIT", qty)

            # 撮合
            self.oms.update(bar)

            # 记录净值
            nav = self.broker.mark_to_market({bar.symbol: bar.close})
            self._nav_history.append((bar.timestamp, nav))

        self._last_date = today
        self._save_state(today)

        return self._report()

    def _current_nav(self, close: float) -> float:
        return self.broker.mark_to_market({"dummy": close})

    def _position_values(self, bar) -> dict:
        return {
            sym: p.get("quantity", 0) * bar.close
            for sym, p in self.broker.positions.items()
        }

    def _calc_qty(self, signal, bar) -> int | None:
        if signal.direction.value == "LONG":
            available = self.broker.cash * 0.95
            qty = int(available / bar.close / 100) * 100
            return qty if qty > 0 else None
        else:
            pos = self.broker.positions.get(bar.symbol, {})
            return pos.get("quantity", 0) or None

    def _liquidate_all(self, bar):
        for sym, pos in list(self.broker.positions.items()):
            if pos.get("quantity", 0) > 0:
                self.oms.submit(sym, "EXIT", pos["quantity"])

    def _report(self) -> dict:
        navs = [n for _, n in self._nav_history]
        latest_nav = navs[-1] if navs else self.initial_cash
        total_return = (latest_nav / self.initial_cash - 1)
        # 简单计算收益
        if len(navs) >= 2:
            rets = [(navs[i] - navs[i-1]) / navs[i-1] for i in range(1, len(navs))]
            vol = (sum((r - sum(rets)/len(rets))**2 for r in rets) / (len(rets)-1)) ** 0.5 if len(rets) > 1 else 0
        else:
            vol = 0

        report = {
            "date": date.today().isoformat(),
            "initial_cash": self.initial_cash,
            "cash": round(self.broker.cash, 2),
            "nav": round(latest_nav, 2),
            "total_return": f"{total_return*100:.2f}%",
            "daily_vol": f"{vol*100:.2f}%" if vol else "N/A",
            "positions": {
                sym: {
                    "qty": p["quantity"],
                    "avg_cost": round(p["avg_cost"], 2),
                }
                for sym, p in self.broker.positions.items()
            },
            "trades_today": self._trade_count_today,
            "total_days": len(set(t.date() for t, _ in self._nav_history)),
        }
        return report

    def _save_state(self, today: date):
        state = {
            "last_date": today.isoformat(),
            "cash": self.broker.cash,
            "positions": self.broker.positions,
            "trades": self.broker.trade_history[-50:],  # 最近 50 笔
            "nav_history": [
                (
                    t.isoformat() if hasattr(t, "isoformat") else str(t),
                    float(n),
                )
                for t, n in self._nav_history[-252:]  # 最近 252 天
            ],
        }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _load_state() -> dict | None:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 还原 nav_history 的 timestamp
            nav = []
            for t_str, n in raw.get("nav_history", []):
                try:
                    ts = datetime.fromisoformat(t_str)
                except Exception:
                    ts = t_str
                nav.append((ts, float(n)))
            raw["nav_history"] = nav
            return raw
        return None


# ═══════════════════════════════════════════
#  命令行入口
# ═══════════════════════════════════════════
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="重置账户")
    parser.add_argument("--strategy", choices=["dual", "turtle", "rsrs"],
                       default="dual", help="选择策略")
    parser.add_argument("--cash", type=int, default=1_000_000, help="初始资金")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("🗑 已重置纸交易账户")

    strategies = {
        "dual": DualMAStrategy(5, 20),
        "turtle": TurtleStrategy(20, 10, 20, 2.0),
        "rsrs": RSRSStrategy(18, 0.5, -0.5),
    }

    runner = DailyPaperRunner(
        strategy=strategies[args.strategy],
        symbols=["sh.000300"],
        initial_cash=args.cash,
    )

    report = runner.run()

    print("\n" + "=" * 50)
    print("  📊 今日纸交易报告")
    print("=" * 50)
    print(f"  日期:      {report['date']}")
    print(f"  净值:      ¥{report['nav']:,.0f}")
    print(f"  现金:      ¥{report['cash']:,.0f}")
    print(f"  总收益:    {report['total_return']}")
    print(f"  今日交易:  {report['trades_today']} 笔")
    print(f"  持仓天数:  {report['total_days']} 天")
    if report["positions"]:
        print(f"  当前持仓:")
        for sym, pos in report["positions"].items():
            print(f"    {sym}: {pos['qty']}股 @¥{pos['avg_cost']:.2f}")
    else:
        print(f"  当前持仓:  空仓")
    print("=" * 50)
    print(f"  状态文件: {STATE_FILE}")
