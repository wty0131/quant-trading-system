"""
多策略组合引擎 — 把多个独立的策略净值合并成组合净值

输入:
  多个策略在同一个数据集上跑的结果（各自的日净值序列）

输出:
  按分配方案加权合并后的组合净值 + BacktestReport

原理:
  1. 每个策略独立回测 → 获取 {策略名: 日收益率序列}
  2. Allocator 根据历史波动率/Sharpe 决定资金分配权重
  3. 按权重合并日收益率 → 组合净值
  4. 生成绩效报告
"""

import numpy as np
import pandas as pd

from backtest.engine import BacktestEngine
from backtest.analytics import generate_report, BacktestReport, TRADING_DAYS
from .allocator import Allocator, InvVolAllocator


class StrategyCombiner:
    """
    多策略组合引擎

    用法:
        combiner = StrategyCombiner(
            strategies={
                "DualMA": DualMAStrategy(5, 20),
                "Turtle": TurtleStrategy(20, 10),
                "RSRS":   RSRSStrategy(18, 0.5, -0.5),
            },
            allocator=InvVolAllocator(),
        )
        report = combiner.run(df_csi)
    """

    def __init__(
        self,
        strategies: dict[str, object],
        allocator: Allocator | None = None,
        initial_cash: float = 1_000_000,
        slippage: float = 0.001,
        commission_rate: float = 0.0003,
    ):
        """
        Args:
            strategies:   {策略名: 策略实例}
            allocator:    资金分配器 (默认 InvVol)
            initial_cash: 总初始资金
            slippage:     滑点
            commission_rate: 手续费率
        """
        self.strategies = strategies
        self.allocator = allocator or InvVolAllocator()
        self.initial_cash = initial_cash
        self.slippage = slippage
        self.commission_rate = commission_rate

        # 存储中间结果
        self.individual_reports: dict[str, BacktestReport] = {}
        self.daily_returns: dict[str, np.ndarray] = {}
        self.combined_nav: list[tuple] = []
        self.weights: dict[str, float] = {}

    def run(self, df: pd.DataFrame) -> BacktestReport:
        """
        执行多策略组合回测

        Args:
            df: 标准 OHLCV DataFrame

        Returns:
            组合级别的 BacktestReport
        """
        # ── Step 1: 每个策略独立回测 ──
        print("=" * 50)
        print("多策略组合回测")
        print("=" * 50)

        for name, strategy in self.strategies.items():
            engine = BacktestEngine(
                df=df,
                strategy=strategy,
                initial_cash=self.initial_cash,
                slippage=self.slippage,
                commission_rate=self.commission_rate,
            )
            report = engine.run()
            self.individual_reports[name] = report

            # 从净值导出日收益率
            navs = np.array([n for _, n in report.nav_history])
            if len(navs) > 1:
                rets = np.diff(navs) / navs[:-1]
                self.daily_returns[name] = rets

            print(f"  {name:12s} return={report.total_return*100:6.2f}%  "
                  f"sharpe={report.sharpe_ratio:6.3f}  MDD={report.max_drawdown*100:6.2f}%")

        if not self.daily_returns:
            return BacktestReport()

        # ── Step 2: 资金分配 ──
        self.weights = self.allocator.allocate(
            self.daily_returns, self.initial_cash
        )
        print(f"\n  资金分配:")
        for name, amount in self.weights.items():
            print(f"    {name:12s} {amount:>12,.0f}  ({amount/self.initial_cash*100:.0f}%)")

        # ── Step 3: 按权重合并日收益率 ──
        # 对齐各策略的收益序列长度
        min_len = min(len(r) for r in self.daily_returns.values())
        weight_pct = {n: w / self.initial_cash for n, w in self.weights.items()}

        combined_rets = np.zeros(min_len)
        for name, rets in self.daily_returns.items():
            combined_rets += weight_pct.get(name, 0) * rets[-min_len:]

        # ── Step 4: 计算组合净值 ──
        first_date = self._get_first_date()
        nav = self.initial_cash * np.cumprod(1 + combined_rets)
        self.combined_nav = [
            (first_date + pd.Timedelta(days=i), float(nav[i]))
            for i in range(len(nav))
        ]

        # 构建虚拟交易记录（汇总）
        all_trades = []
        for name, report in self.individual_reports.items():
            # 按权重缩放每笔交易
            pass
        all_trades = self._merge_trades()

        # ── Step 5: 生成组合报告 ──
        report = generate_report(
            nav_history=[(first_date, self.initial_cash)] + self.combined_nav[1:],
            trades=all_trades,
            initial_cash=self.initial_cash,
        )

        print(f"\n  组合:  return={report.total_return*100:.2f}%  "
              f"sharpe={report.sharpe_ratio:.3f}  MDD={report.max_drawdown*100:.2f}%")

        return report

    def _get_first_date(self):
        """从第一个报告获取起始日期"""
        for r in self.individual_reports.values():
            if r.nav_history:
                return r.nav_history[0][0]
        return pd.Timestamp.now()

    def _merge_trades(self) -> list[dict]:
        """合并所有策略的交易记录"""
        # 简化：策略本身不导出交易列表，我们通过 on_bar 信号来记录
        return []

    def get_correlation_matrix(self) -> pd.DataFrame:
        """策略日收益相关性矩阵"""
        if len(self.daily_returns) < 2:
            return pd.DataFrame()
        # 对齐长度
        min_len = min(len(r) for r in self.daily_returns.values())
        data = {}
        for name, rets in self.daily_returns.items():
            data[name] = rets[-min_len:]
        return pd.DataFrame(data).corr()

    def individual_sharpes(self) -> dict[str, float]:
        """各策略的 Sharpe"""
        return {n: r.sharpe_ratio for n, r in self.individual_reports.items()}
