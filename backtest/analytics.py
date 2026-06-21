"""
绩效分析 — 回测报告生成

指标：
  - 总收益 / 年化收益
  - 夏普比率 / 索提诺比率
  - 最大回撤 / 卡尔玛比率
  - 胜率 / 盈亏比
  - 交易统计
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field

TRADING_DAYS = 252
RISK_FREE_RATE = 0.025


@dataclass
class BacktestReport:
    """回测报告"""
    # 收益指标
    total_return: float = 0.0
    annual_return: float = 0.0
    annual_volatility: float = 0.0

    # 风险指标
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    calmar_ratio: float = 0.0

    # 交易统计
    total_trades: int = 0
    win_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0

    # 持仓统计
    position_days: int = 0
    total_days: int = 0
    position_ratio: float = 0.0

    # 净值
    initial_cash: float = 0.0
    final_nav: float = 0.0
    nav_history: list = field(default_factory=list)

    def __repr__(self) -> str:
        lines = []
        lines.append("=" * 55)
        lines.append(f"{'回测绩效报告':^45}")
        lines.append("=" * 55)
        lines.append(f"  总收益率:    {self.total_return*100:>8.2f}%")
        lines.append(f"  年化收益率:  {self.annual_return*100:>8.2f}%")
        lines.append(f"  年化波动率:  {self.annual_volatility*100:>8.2f}%")
        lines.append(f"  ───────────────────────────────────")
        lines.append(f"  夏普比率:    {self.sharpe_ratio:>8.3f}")
        lines.append(f"  索提诺比率:  {self.sortino_ratio:>8.3f}")
        lines.append(f"  最大回撤:    {self.max_drawdown*100:>8.2f}%")
        lines.append(f"  卡尔玛比率:  {self.calmar_ratio:>8.3f}")
        lines.append(f"  ───────────────────────────────────")
        lines.append(f"  总交易次数:  {self.total_trades:>8d}")
        lines.append(f"  胜率:        {self.win_rate*100:>8.1f}%")
        lines.append(f"  盈亏比:      {self.profit_factor:>8.2f}")
        lines.append(f"  ───────────────────────────────────")
        lines.append(f"  初始资金:    {self.initial_cash:>12,.0f}")
        lines.append(f"  最终净值:    {self.final_nav:>12,.0f}")
        lines.append(f"  持仓占比:    {self.position_ratio*100:>8.1f}%")
        lines.append("=" * 55)
        return "\n".join(lines)


def generate_report(
    nav_history: list[tuple],
    trades: list[dict],
    initial_cash: float,
) -> BacktestReport:
    """
    生成回测报告

    Args:
        nav_history: [(timestamp, nav), ...]
        trades:      [{timestamp, symbol, direction, price, quantity, commission}, ...]
        initial_cash: 初始资金
    """
    report = BacktestReport()
    report.initial_cash = initial_cash

    if not nav_history:
        return report

    # ── 净值分析 ──
    timestamps = [t for t, _ in nav_history]
    navs = np.array([n for _, n in nav_history])
    report.nav_history = [(t, float(n)) for t, n in nav_history]
    report.total_days = len(navs)

    if report.total_days > 1:
        # 收益率
        report.final_nav = float(navs[-1])
        report.total_return = float((navs[-1] / initial_cash) - 1)

        # 日收益率
        returns = np.diff(navs) / navs[:-1]
        report.annual_return = float(np.mean(returns) * TRADING_DAYS)
        report.annual_volatility = float(np.std(returns, ddof=1) * np.sqrt(TRADING_DAYS))

        # 夏普
        if report.annual_volatility > 0:
            report.sharpe_ratio = float(
                (report.annual_return - RISK_FREE_RATE) / report.annual_volatility
            )

        # 索提诺（只算下行波动率）
        downside = returns[returns < 0]
        if len(downside) > 1:
            downside_vol = float(np.std(downside, ddof=1) * np.sqrt(TRADING_DAYS))
            if downside_vol > 0:
                report.sortino_ratio = float(
                    (report.annual_return - RISK_FREE_RATE) / downside_vol
                )

        # 最大回撤
        running_max = np.maximum.accumulate(navs)
        drawdowns = (navs - running_max) / running_max
        report.max_drawdown = float(np.min(drawdowns))

        # 卡尔玛
        if abs(report.max_drawdown) > 0:
            report.calmar_ratio = float(report.annual_return / abs(report.max_drawdown))

    # ── 交易分析 ──
    if trades:
        report.total_trades = len(trades)
        pnls = []
        for t in trades:
            if t["direction"] in ("EXIT", "卖出"):
                pnl = (t["price"] - t.get("entry_price", t["price"])) * t["quantity"]
            else:
                pnl = 0  # 开仓不计盈亏
            pnls.append(pnl)

        # 用更直接的方式：每笔平仓交易的盈亏
        # 先建仓后平仓配对
        entry_price = None
        entry_qty = 0
        trade_pnls = []

        for t in trades:
            if t["direction"] in ("LONG", "买入"):
                # 加权平均开仓价
                if entry_price is None:
                    entry_price = t["price"]
                    entry_qty = t["quantity"]
                else:
                    total_cost = entry_price * entry_qty + t["price"] * t["quantity"]
                    entry_qty += t["quantity"]
                    entry_price = total_cost / entry_qty

            elif t["direction"] in ("EXIT", "卖出") and entry_price is not None:
                gross_pnl = (t["price"] - entry_price) * t["quantity"]
                net_pnl = gross_pnl - t.get("commission", 0)
                trade_pnls.append(net_pnl)
                entry_price = None
                entry_qty = 0

        if trade_pnls:
            trade_pnls = np.array(trade_pnls)
            wins = trade_pnls[trade_pnls > 0]
            losses = trade_pnls[trade_pnls < 0]
            report.win_trades = len(wins)
            report.win_rate = float(len(wins) / len(trade_pnls))
            report.avg_win = float(np.mean(wins)) if len(wins) > 0 else 0
            report.avg_loss = float(abs(np.mean(losses))) if len(losses) > 0 else 0

            total_profit = float(np.sum(wins)) if len(wins) > 0 else 0
            total_loss = float(abs(np.sum(losses))) if len(losses) > 0 else 0
            if total_loss > 0:
                report.profit_factor = float(total_profit / total_loss)

        # 持仓天数
        in_position = False
        pos_days = 0
        trade_idx = 0
        for t, _ in nav_history:
            while trade_idx < len(trades) and trades[trade_idx]["timestamp"] <= t:
                td = trades[trade_idx]
                if td["direction"] in ("LONG", "买入"):
                    in_position = True
                elif td["direction"] in ("EXIT", "卖出"):
                    in_position = False
                trade_idx += 1
            if in_position:
                pos_days += 1
        report.position_days = pos_days
        report.position_ratio = float(pos_days / max(report.total_days, 1))

    return report
