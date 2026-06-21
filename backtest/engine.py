"""
回测引擎 — 事件驱动主循环

组装 DataHandler + Strategy + Portfolio + ExecutionHandler，
按时间顺序逐条播放历史数据，记录每一根K线的决策和结果。

用法:
    from backtest import BacktestEngine
    from backtest.strategy import DualMAStrategy

    engine = BacktestEngine(
        df=ohlcv_dataframe,
        strategy=DualMAStrategy(short=5, long=20),
        initial_cash=1_000_000,
    )
    report = engine.run()
    print(report)
"""

import pandas as pd

from .event import MarketEvent, Direction
from .strategy import Strategy, BuyAndHoldStrategy
from .portfolio import Portfolio
from .execution import ExecutionHandler
from .analytics import generate_report, BacktestReport


class BacktestEngine:
    """
    回测引擎

    职责：
      1. 从 DataFrame 逐条回放数据
      2. 调用 strategy.on_bar()
      3. 处理信号 → 订单 → 成交 → 组合更新
      4. 记录每日净值和交易明细
      5. 生成绩效报告
    """

    def __init__(
        self,
        df: pd.DataFrame,
        strategy: Strategy,
        initial_cash: float = 1_000_000,
        slippage: float = 0.001,
        commission_rate: float = 0.0003,
        position_percent: float = 1.0,
        lot_size: int = 100,
    ):
        """
        Args:
            df:               标准 OHLCV DataFrame
            strategy:         策略实例
            initial_cash:     初始资金
            slippage:         滑点比例
            commission_rate:  手续费率
            position_percent: 每次开仓使用资金比例
            lot_size:         最小交易单位（A股=100，指数/加密=1）
        """
        # 数据
        self.df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

        # 组件
        self.strategy = strategy
        self.portfolio = Portfolio(
            initial_cash=initial_cash,
            position_percent=position_percent,
            lot_size=lot_size,
        )
        self.execution = ExecutionHandler(
            slippage=slippage,
            commission_rate=commission_rate,
        )

        # 记录
        self.trades: list[dict] = []

    def run(self) -> BacktestReport:
        """
        执行回测

        Returns:
            BacktestReport — 完整绩效报告
        """
        # 按日期分组，将同一天的多只股票数据打包
        # 但为简化，单 symbol 逐条处理（多 symbol 按日分组）

        symbols = self.df["symbol"].unique()

        if len(symbols) == 1:
            return self._run_single(symbols[0])
        else:
            return self._run_multi(symbols)

    def _run_single(self, symbol: str) -> BacktestReport:
        """单品种回测"""
        data = self.df[self.df["symbol"] == symbol].sort_values("date")

        for _, row in data.iterrows():
            # 1. 构建 MarketEvent
            bar = MarketEvent.from_row(row.to_dict())

            # 2. 策略分析
            signal = self.strategy.on_bar(bar)

            # 3. 信号 → 订单 → 成交 → 更新
            if signal is not None:
                order = self.portfolio.generate_order(signal, bar.close)
                if order is not None:
                    fill = self.execution.execute(order, bar.__dict__)
                    self.portfolio.update(fill)
                    self.trades.append({
                        "timestamp": fill.timestamp,
                        "symbol": fill.symbol,
                        "direction": fill.direction.value,
                        "price": fill.price,
                        "quantity": fill.quantity,
                        "commission": fill.commission,
                    })

            # 4. 每日按市价计算净值
            self.portfolio.mark_to_market(bar.timestamp, {symbol: bar.close})

        return generate_report(
            nav_history=self.portfolio.nav_history,
            trades=self.trades,
            initial_cash=self.portfolio.initial_cash,
        )

    def _run_multi(self, symbols: list[str]) -> BacktestReport:
        """多品种回测 — 按日期分组处理"""
        # 按日期分组
        for date, group in self.df.groupby("date"):
            timestamp = date

            for _, row in group.iterrows():
                symbol = row["symbol"]
                bar = MarketEvent.from_row(row.to_dict())

                # 策略分析
                signal = self.strategy.on_bar(bar)

                if signal is not None:
                    order = self.portfolio.generate_order(signal, bar.close)
                    if order is not None:
                        fill = self.execution.execute(order, bar.__dict__)
                        self.portfolio.update(fill)
                        self.trades.append({
                            "timestamp": fill.timestamp,
                            "symbol": fill.symbol,
                            "direction": fill.direction.value,
                            "price": fill.price,
                            "quantity": fill.quantity,
                            "commission": fill.commission,
                        })

            # 每日按市价计算所有持仓净值
            prices = {r["symbol"]: r["close"] for _, r in group.iterrows()}
            self.portfolio.mark_to_market(timestamp, prices)

        return generate_report(
            nav_history=self.portfolio.nav_history,
            trades=self.trades,
            initial_cash=self.portfolio.initial_cash,
        )
