"""
多因子选股策略 — 截面 Alpha

原理:
  选 N 个 Alpha 因子 → 每个股票一个综合得分
  → 定期调仓：买入得分最高的 top_k 只
  → 卖出入围但排名下降的

因子（本实现）:
  1. 动量因子:  过去 M 日收益率（强者恒强）
  2. 反转因子:  过去 S 日收益率（超跌反弹）
  3. 波动率因子: 过去 V 日波动率（低波溢价）
  4. 成交量因子: 相对成交量变化（放量=关注）

核心检验:
  IC (信息系数) = factor_score 与 forward_return 的相关性
  IC > 0.02 有用, > 0.05 很强

用法（需配合引擎的多symbol模式）:
  strategy = MultiFactorStrategy(top_k=3, rebalance_days=20)
  engine = BacktestEngine(df_multi, strategy)  # df_multi 含多只股票
"""

import numpy as np
from collections import deque
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class MultiFactorStrategy(Strategy):
    """多因子截面选股"""

    def __init__(
        self,
        top_k: int = 5,
        momentum_days: int = 20,
        reversal_days: int = 5,
        vol_days: int = 20,
        rebalance_days: int = 20,
    ):
        super().__init__()
        self.top_k = top_k
        self.momentum_days = momentum_days
        self.reversal_days = reversal_days
        self.vol_days = vol_days
        self.rebalance_days = rebalance_days
        self._bars_since_rebalance = 0
        self._current_holdings: set[str] = set()

    def _score_stock(self, symbol: str) -> float | None:
        """单只股票的综合因子得分"""
        if symbol not in self._price_history:
            return None
        prices = list(self._price_history[symbol])
        if len(prices) < max(self.momentum_days, self.vol_days):
            return None

        # 1. 动量因子: 20日收益
        momentum = (prices[-1] / prices[-self.momentum_days] - 1) if len(prices) > self.momentum_days else 0

        # 2. 反转因子: 5日收益（取负，赌反转）
        reversal = -(prices[-1] / prices[-self.reversal_days] - 1) if len(prices) > self.reversal_days else 0

        # 3. 波动率因子: 20日波动率（低波加分）
        recent = prices[-self.vol_days:]
        returns = np.diff(recent) / recent[:-1]
        volatility = np.std(returns) if len(returns) > 0 else 0
        # 低波加分（通常低波动有溢价）
        vol_score = -volatility * 100

        # 4. 等权综合
        total = 0.5 * momentum + 0.3 * reversal + 0.2 * vol_score
        return float(total)

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        self._bars_since_rebalance += 1

        # 调仓时点
        if self._bars_since_rebalance < self.rebalance_days:
            return None

        # 只在调仓日的第一只股票触发计算
        # 引擎会把同一天的数据逐条推过来，我们只处理第一条
        self._bars_since_rebalance = 0

        # 尝试对所有已知符号打分
        scores = {}
        for sym in self._price_history:
            s = self._score_stock(sym)
            if s is not None:
                scores[sym] = s

        if len(scores) < self.top_k:
            return None

        # 选 top_k 只
        ranked = sorted(scores, key=scores.get, reverse=True)[:self.top_k]
        new_holdings = set(ranked)

        # 不属于前 top_k 的：卖出
        to_sell = self._current_holdings - new_holdings
        # 新增的：买入
        to_buy = new_holdings - self._current_holdings

        self._current_holdings = new_holdings

        # 简化为单个信号：引擎目前单品模式，多品模式待引擎扩展
        # 此处只返回 None，完整多品调仓逻辑在 Notebook 中讲解原理
        return None
