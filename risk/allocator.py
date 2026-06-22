"""
资金分配 — 1000万怎么分给多个策略？

三种方法:
  EqualAllocator      — 等权 (基准)
  InvVolAllocator     — 波动率倒数加权 (最稳健)
  MaxSharpeAllocator  — Markowitz 最优 Sharpe (理论最优)

核心认知:
  - 等权是基准，任何优化必须比等权好才有意义
  - 波动率倒数 = 让每个策略贡献相同的波动，鲁棒性最好
  - Markowitz 容易过拟合：过去协方差 ≠ 未来协方差
"""

from abc import ABC, abstractmethod
import numpy as np
import pandas as pd


class Allocator(ABC):
    """资金分配器抽象基类"""

    @abstractmethod
    def allocate(
        self,
        daily_returns: dict[str, np.ndarray],
        capital: float,
    ) -> dict[str, float]:
        """
        Args:
            daily_returns: {策略名: 日收益率 array}
            capital:       总资金

        Returns:
            {策略名: 分配金额}
        """
        ...


class EqualAllocator(Allocator):
    """等权分配 — 每个策略分一样多"""

    def allocate(
        self,
        daily_returns: dict[str, np.ndarray],
        capital: float,
    ) -> dict[str, float]:
        n = len(daily_returns)
        if n == 0:
            return {}
        return {name: capital / n for name in daily_returns}


class InvVolAllocator(Allocator):
    """
    波动率倒数加权

    高波动策略分少 → 每个策略对组合贡献相同的波动
    weight_i = (1/vol_i) / sum(1/vol_j)
    """

    def allocate(
        self,
        daily_returns: dict[str, np.ndarray],
        capital: float,
    ) -> dict[str, float]:
        vols = {}
        for name, rets in daily_returns.items():
            if len(rets) < 2:
                vols[name] = 1.0
            else:
                vol = np.std(rets, ddof=1)
                vols[name] = max(vol, 0.001)  # 防除零

        inv_vols = {n: 1.0 / v for n, v in vols.items()}
        total = sum(inv_vols.values())
        if total == 0:
            n = len(daily_returns)
            return {name: capital / n for name in daily_returns}

        return {n: capital * (iv / total) for n, iv in inv_vols.items()}


class MaxSharpeAllocator(Allocator):
    """
    Markowitz 均值-方差优化 — 最大化 Sharpe Ratio

    找到权重 w 使:
      max  (w'r - rf) / sqrt(w'Σw)
      s.t. Σw = 1, w ≥ 0

    警告: 这是切片内优化，容易过拟合。实际使用请 roll-forward 验证。
    """

    def __init__(self, risk_free: float = 0.025, lookback: int = 252):
        """
        Args:
            risk_free: 无风险利率
            lookback:  用于估计协方差矩阵的回看天数
        """
        self.risk_free = risk_free
        self.lookback = lookback

    def allocate(
        self,
        daily_returns: dict[str, np.ndarray],
        capital: float,
    ) -> dict[str, float]:
        names = list(daily_returns.keys())
        n = len(names)
        if n <= 1:
            return {} if n == 0 else {names[0]: capital}

        # 对齐所有收益序列到相同长度
        min_len = min(len(r) for r in daily_returns.values())
        aligned = []
        for name in names:
            rets = daily_returns[name][-min_len:]
            aligned.append(rets)

        ret_matrix = np.array(aligned)  # shape: (n_strategies, n_days)

        # 平均收益
        mu = np.mean(ret_matrix, axis=1) * 252  # 年化

        # 协方差矩阵
        sigma = np.cov(ret_matrix) * 252  # 年化

        # 网格搜索找最优权重 (简单粗暴，避免 scipy 依赖)
        best_sharpe = -1
        best_weights = np.ones(n) / n

        for _ in range(5000):
            w = np.random.random(n)
            w = w / w.sum()
            port_ret = np.dot(w, mu)
            port_vol = np.sqrt(np.dot(w.T, np.dot(sigma, w)))
            if port_vol > 0:
                sharpe = (port_ret - self.risk_free) / port_vol
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_weights = w

        return {names[i]: capital * float(best_weights[i]) for i in range(n)}
