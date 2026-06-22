"""
独立风控守护 — 不与策略同进程

为什么必须独立？
  - 策略代码在另一进程/线程中运行
  - 策略 crash 了 → 风控仍在运行 → 能强制平仓
  - 策略"疯了"（连续报单）→ 风控能切断

不能把止损逻辑写在策略的 on_bar() 里——
策略自己不能裁判自己。

风控规则:
  DailyLossLimit  — 当日亏损超过 X% → 锁定禁止开仓
  MaxDrawdown     — 从峰值回撤超过 X% → 全部平仓
  PositionLimit   — 单品种仓位超过 X% → 拒绝该品种新单
  TotalExposure   — 总仓位超过 X% → 拒绝所有新单
"""

from datetime import datetime, date
from enum import Enum


class RiskAction(str, Enum):
    ALLOW = "allow"
    BLOCK_BUY = "block_buy"     # 只能平仓不能开仓
    LIQUIDATE_ALL = "liquidate"  # 全部平仓
    BLOCKED = "blocked"          # 所有操作被禁止


class RiskGuard:
    """独立风控守护"""

    def __init__(
        self,
        max_daily_loss: float = 0.05,      # 日亏损上限 5%
        max_drawdown: float = 0.20,         # 最大回撤 20%
        max_position_pct: float = 0.30,     # 单品种仓位上限 30%
        max_total_exposure: float = 0.80,   # 总仓位上限 80%
    ):
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
        self.max_position_pct = max_position_pct
        self.max_total_exposure = max_total_exposure

        # 状态
        self._initial_cash = 0.0
        self._peak_nav = 0.0        # 历史最高净值
        self._day_start_nav = 0.0   # 当日开盘净值
        self._current_date = None

    def initialize(self, initial_cash: float, current_nav: float, today: date):
        """初始化/重置"""
        self._initial_cash = initial_cash
        self._peak_nav = current_nav
        self._day_start_nav = current_nav
        self._current_date = today

    def check(
        self,
        current_nav: float,
        positions: dict[str, float],      # {symbol: position_value}
        today: date | None = None,
    ) -> tuple[RiskAction, str]:
        """
        检查所有风控规则

        Args:
            current_nav: 当前总净值
            positions:   各品种持仓市值 {symbol: market_value}
            today:       当前日期

        Returns:
            (RiskAction, 原因描述)
        """
        if today and today != self._current_date:
            # 新交易日，重置日亏损记录
            self._day_start_nav = current_nav
            self._current_date = today

        # 更新峰值
        self._peak_nav = max(self._peak_nav, current_nav)

        # ── 规则1: 最大回撤 ──
        drawdown = (current_nav - self._peak_nav) / self._peak_nav
        if abs(drawdown) > self.max_drawdown:
            return RiskAction.LIQUIDATE_ALL, f"最大回撤触发: {drawdown*100:.1f}% > {self.max_drawdown*100:.0f}%"

        # ── 规则2: 日亏损上限 ──
        if self._day_start_nav > 0:
            daily_loss = (current_nav - self._day_start_nav) / self._day_start_nav
            if daily_loss < -self.max_daily_loss:
                return RiskAction.BLOCK_BUY, f"日亏损触发: {daily_loss*100:.1f}% < -{self.max_daily_loss*100:.0f}%"

        # ── 规则3: 单品种仓位 ──
        for sym, value in positions.items():
            if current_nav > 0:
                pct = value / current_nav
                if pct > self.max_position_pct:
                    return RiskAction.BLOCK_BUY, f"{sym} 仓位超标: {pct*100:.1f}% > {self.max_position_pct*100:.0f}%"

        # ── 规则4: 总仓位 ──
        total_exposure = sum(positions.values()) / max(current_nav, 1)
        if total_exposure > self.max_total_exposure:
            return RiskAction.BLOCK_BUY, f"总仓位超标: {total_exposure*100:.1f}% > {self.max_total_exposure*100:.0f}%"

        return RiskAction.ALLOW, "OK"

    def day_start_nav(self) -> float:
        return self._day_start_nav

    def peak_nav(self) -> float:
        return self._peak_nav
