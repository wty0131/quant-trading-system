"""
纸交易引擎 — 回测引擎的"实盘版"

与 BacktestEngine 的核心区别:
  ┌──────────────────┬──────────────────┬──────────────────┐
  │  回测引擎          │  纸交易引擎        │  实盘引擎         │
  ├──────────────────┼──────────────────┼──────────────────┤
  │ df.iterrows()    │ 每隔N秒拉取       │ 交易所推送        │
  │ SQLite 历史数据   │ baostock最新日线   │ WebSocket实时     │
  │ 全量数据一口气跑  │ 等数据到来再处理   │ 等数据到来再处理   │
  └──────────────────┴──────────────────┴──────────────────┘

纸交易引擎适合:
  - 日线策略 (A股 T+1，每天收盘后跑一次即可)
  - 验证策略逻辑在"真实时间线"上的表现
  - 与回测结果对比偏差 (滑点/延迟的真实成本)
"""

import time
import pandas as pd
from datetime import datetime, date
from collections import deque

from backtest.event import MarketEvent
from backtest.strategy import Strategy
from backtest.analytics import generate_report, BacktestReport
from .paper_broker import PaperBroker
from .oms import OrderManager
from .risk_guard import RiskGuard, RiskAction


class PaperTradingEngine:
    """
    纸交易引擎

    用法 (日线策略):
        engine = PaperTradingEngine(
            strategy=DualMAStrategy(5, 20),
            symbols=["sh.000300"],
            initial_cash=1_000_000,
        )
        engine.run_daily()  # 每天收盘后调用一次
    """

    def __init__(
        self,
        strategy: Strategy,
        symbols: list[str],
        initial_cash: float = 1_000_000,
        slippage: float = 0.001,
        commission_rate: float = 0.0003,
    ):
        self.strategy = strategy
        self.symbols = symbols
        self.initial_cash = initial_cash

        # 组件
        self.broker = PaperBroker(
            initial_cash=initial_cash,
            slippage=slippage,
            commission_rate=commission_rate,
        )
        self.oms = OrderManager(self.broker, timeout_seconds=300)
        self.guard = RiskGuard()

        # 状态
        self._nav_history: list[tuple] = []
        self._current_date: date | None = None
        self._bar_count = 0
        self._price_history: dict[str, deque[float]] = {}

    def on_market_data(self, bar: MarketEvent):
        """
        收到实时行情 — 纸交易核心循环

        与 BacktestEngine._run_single() 结构完全一致:
          1. 策略分析
          2. 信号→订单
          3. 成交处理
          4. 风控检查
          5. 更新净值

        区别: 成交是异步的 (OMS管理)，不是立即执行
        """

        # 检查新交易日
        bar_date = bar.timestamp.date() if hasattr(bar.timestamp, "date") else bar.timestamp
        if self._current_date is None or bar_date != self._current_date:
            self._on_new_day(bar_date)

        # 1. 策略分析
        signal = self.strategy.on_bar(bar)

        # 2. 风控检查
        nav = self.broker.mark_to_market({bar.symbol: bar.close})
        action, reason = self.guard.check(
            nav,
            positions=self._position_values(bar),
            today=bar_date,
        )

        # 3. 信号→订单 (风控放行才下单)
        if signal is not None:
            if action == RiskAction.ALLOW:
                # 生成订单量
                from backtest.portfolio import Portfolio
                import sys
                # 使用 broker 的现金和持仓信息计算订单量
                qty = self._calc_quantity(signal, bar)
                if qty > 0:
                    oid = self.oms.submit(
                        symbol=bar.symbol,
                        direction=signal.direction.value,
                        quantity=qty,
                    )
            elif action == RiskAction.LIQUIDATE_ALL:
                # 强制全部平仓
                self._liquidate_all(bar)
            elif action == RiskAction.BLOCK_BUY:
                # 可以平仓但不能开仓
                if signal.direction.value == "EXIT":
                    qty = self._calc_quantity(signal, bar)
                    if qty > 0:
                        self.oms.submit(bar.symbol, signal.direction.value, qty)

        # 4. 处理所有挂单
        fills = self.oms.update(bar)

        # 5. 更新净值
        nav = self.broker.mark_to_market({bar.symbol: bar.close})
        self._nav_history.append((bar.timestamp, nav))
        self._bar_count += 1

    def _calc_quantity(self, signal, bar) -> int:
        """计算订单量 (简化: 全仓买卖)"""
        if signal.direction.value == "LONG":
            available = self.broker.cash * 0.95
            qty = int(available / bar.close / 100) * 100  # 整手
            return qty
        else:
            pos = self.broker.positions.get(bar.symbol, {})
            return pos.get("quantity", 0)

    def _position_values(self, bar) -> dict[str, float]:
        """各品种持仓市值"""
        vals = {}
        for sym, pos in self.broker.positions.items():
            vals[sym] = pos.get("quantity", 0) * bar.close
        return vals

    def _liquidate_all(self, bar):
        """强制全部平仓"""
        for sym, pos in list(self.broker.positions.items()):
            if pos.get("quantity", 0) > 0:
                self.oms.submit(sym, "EXIT", pos["quantity"])

    def _on_new_day(self, today: date):
        """新交易日重置"""
        nav = self.broker.cash + sum(
            p.get("quantity", 0) * p.get("avg_cost", 0)
            for p in self.broker.positions.values()
        )
        self.guard.initialize(self.initial_cash, nav, today)

    # ── 日线回放模式 (用 SQLite 历史数据模拟实盘) ──

    def replay_from_store(self, df: pd.DataFrame) -> BacktestReport:
        """
        用历史数据回放纸交易过程

        这不是回测——它走的是 PaperBroker + OMS 的真实路径，
        只是数据来源是历史 SQLite。用于对比:
          - BacktestEngine (假设立即成交)
          - PaperTradingEngine (走OMS+模拟延迟)

        两者结果的差异 = 执行层的摩擦成本
        """
        print("纸交易回放 (PaperBroker + OMS + RiskGuard)")
        print(f"  数据: {len(df)} 行, {df['symbol'].nunique()} 只")
        print(f"  初始资金: {self.initial_cash:,.0f}")

        for _, row in df.sort_values("date").iterrows():
            bar = MarketEvent.from_row(row.to_dict())
            self.on_market_data(bar)

        # 生成报告
        report = generate_report(
            nav_history=self._nav_history,
            trades=self.broker.trade_history,
            initial_cash=self.initial_cash,
        )
        print(f"  收益: {report.total_return*100:.2f}%  "
              f"Sharpe: {report.sharpe_ratio:.3f}  "
              f"MDD: {report.max_drawdown*100:.2f}%")
        return report
