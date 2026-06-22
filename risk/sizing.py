"""
仓位管理 — 每次开仓该买多少？

四种模型:
  FixedFractionSizer — 固定比例 (最简单)
  KellySizer          — Kelly 公式 (理论最优，实践中打折扣)
  RiskParitySizer     — 风险平价 (每份头寸承担相同风险)
  VolTargetSizer      — 波动率目标 (动态调整维持目标波动率)
"""

from abc import ABC, abstractmethod
import numpy as np


class Sizer(ABC):
    """仓位计算器抽象基类"""

    @abstractmethod
    def get_position_pct(self, cash: float, price: float, **context) -> float:
        """
        返回用于开仓的资金比例 (0~1)

        Args:
            cash:    当前可用资金
            price:   当前价格
            context: 额外上下文 (波动率、胜率等，各子类不同)
        """
        ...


class FixedFractionSizer(Sizer):
    """固定比例 — 每次用 X% 资金"""

    def __init__(self, fraction: float = 0.2):
        self.fraction = fraction

    def get_position_pct(self, cash: float, price: float, **context) -> float:
        return self.fraction


class KellySizer(Sizer):
    """
    Kelly 公式 — 理论最优下注比例

    f* = (p × b - (1-p)) / b
      p = 胜率
      b = 盈亏比 (盈利均值 / 亏损均值)

    安全措施:
      - half_kelly: 只用 f*/2 (标准做法)
      - max_fraction: 上限 25% (防止 f* 过高)
      - min_fraction: 下限 2%  (防止 f* 为负)
    """

    def __init__(
        self,
        win_rate: float = 0.45,
        profit_factor: float = 2.0,
        half: bool = True,
        max_fraction: float = 0.25,
    ):
        self.win_rate = win_rate
        self.profit_factor = profit_factor
        self.half = half
        self.max_fraction = max_fraction

    def get_position_pct(self, cash: float, price: float, **context) -> float:
        p = self.win_rate
        b = self.profit_factor
        if p <= 0 or b <= 0:
            return 0.02  # 最低2%

        # f* = (p*b - (1-p)) / b
        f_star = max(0, (p * b - (1 - p)) / b)

        if self.half:
            f_star /= 2.0

        return min(f_star, self.max_fraction)


class RiskParitySizer(Sizer):
    """
    风险平价 — 让每个头寸贡献相同的波动

    高波动品种买少，低波动品种买多
    position_pct = target_risk / vol
    """

    def __init__(self, target_risk: float = 0.05):
        """
        Args:
            target_risk: 每笔交易目标承担的年化波动（如 0.05 = 5%）
        """
        self.target_risk = target_risk

    def get_position_pct(self, cash: float, price: float, **context) -> float:
        # vol 是年化波动率（由 context 传入）
        vol = context.get("volatility", 0.20)  # 默认20%
        if vol <= 0:
            return 0.1
        pct = self.target_risk / vol
        return min(pct, 0.5)  # 上限50%


class VolTargetSizer(Sizer):
    """
    波动率目标 — 动态调整仓位维持目标波动

    最近波动大 → 自动减仓
    最近波动小 → 自动加仓

    position = target_vol / realized_vol
    """

    def __init__(self, target_vol: float = 0.15, max_leverage: float = 2.0):
        """
        Args:
            target_vol:   目标年化波动率 (如 15%)
            max_leverage: 最大杠杆倍数
        """
        self.target_vol = target_vol
        self.max_leverage = max_leverage

    def get_position_pct(self, cash: float, price: float, **context) -> float:
        # realized_vol 是年化波动率（最近 N 天）
        realized_vol = context.get("realized_vol", 0.20)
        if realized_vol <= 0:
            return 0.2
        pct = self.target_vol / realized_vol
        return min(pct, self.max_leverage)
