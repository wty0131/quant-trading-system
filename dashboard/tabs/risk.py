"""风控页 — 风险仪表 + 仓位监控 + 风控规则"""
import streamlit as st
import pandas as pd
import numpy as np

from dashboard.components import position_pie
from execution.risk_guard import RiskGuard, RiskAction
from backtest.engine import BacktestEngine
from backtest.strategy import DualMAStrategy
from strategies.turtle import TurtleStrategy
from data.store import DataStore


def show():
    st.title("🛡️ 风控面板")

    # ── 加载数据 ──
    store = DataStore("data/quant.db")
    df = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01")

    if df.empty:
        from data.sources.ashare import AShareSource
        ashare = AShareSource()
        df = ashare.get_history(["sh.000300"], "2024-01-01", "2024-12-31")
        store.save(df, "ashare", "daily")

    # 跑回测获取净值历史
    engine = BacktestEngine(df, TurtleStrategy(20, 10, 20, 2.0), 1_000_000, 0.001, 0.0003)
    report = engine.run()

    navs = np.array([n for _, n in report.nav_history])
    dates = [t for t, _ in report.nav_history]

    # ── 风控检查 ──
    guard = RiskGuard(max_daily_loss=0.05, max_drawdown=0.20,
                      max_position_pct=0.30, max_total_exposure=0.80)
    if navs.size > 0:
        guard.initialize(1_000_000, navs[0], pd.Timestamp("2024-01-02").date())

    # 模拟当前状态
    current_nav = float(navs[-1]) if navs.size > 0 else 1_000_000
    positions_value = {"沪深300": max(0, current_nav * 0.42)}  # 假设42%仓位
    action, reason = guard.check(current_nav, positions_value, pd.Timestamp("2024-12-31").date())

    # ── 第一行：风险仪表 ──
    st.subheader("📊 风险仪表")
    c1, c2, c3, c4 = st.columns(4)

    daily_change = (navs[-1] - navs[-2]) / navs[-2] * 100 if len(navs) > 1 else 0
    peak = np.max(navs) if navs.size > 0 else current_nav
    current_dd = (current_nav - peak) / peak * 100 if peak > 0 else 0

    with c1:
        status = "🟢" if daily_change > -1 else ("🟡" if daily_change > -3 else "🔴")
        st.metric("当日变动", f"{status} {daily_change:+.2f}%",
                  delta=f"日上限 -5%", delta_color="off")
    with c2:
        status = "🟢" if abs(current_dd) < 10 else ("🟡" if abs(current_dd) < 20 else "🔴")
        st.metric("当前回撤", f"{status} {current_dd:.2f}%",
                  delta=f"上限 -20%", delta_color="off")
    with c3:
        pos_pct = sum(positions_value.values()) / max(current_nav, 1) * 100
        status = "🟢" if pos_pct < 50 else ("🟡" if pos_pct < 80 else "🔴")
        st.metric("总仓位", f"{status} {pos_pct:.0f}%",
                  delta=f"上限 80%", delta_color="off")
    with c4:
        status = "🟢" if action == RiskAction.ALLOW else ("🟡" if action == RiskAction.BLOCK_BUY else "🔴")
        st.metric("风控状态", f"{status} {action.value}",
                  delta=reason[:30], delta_color="off")

    # ── 第二行：净值 + 回撤 ──
    st.divider()
    col_chart, col_pie = st.columns([3, 1])

    with col_chart:
        st.subheader("净值 + 回撤线")

        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5), gridspec_kw={"height_ratios": [3, 1]})

        ax1.plot(dates, navs / 1_000_000, "steelblue", lw=1.2)
        ax1.axhline(y=1, color="gray", ls="--", alpha=0.3)
        # 峰值线
        running_max = np.maximum.accumulate(navs)
        ax1.plot(dates, running_max / 1_000_000, "green", lw=0.8, alpha=0.5, ls="--")
        ax1.set_ylabel("Net Value"); ax1.grid(True, alpha=0.3)
        ax1.legend(["NAV", "Peak"], fontsize=8)

        dd = (navs - running_max) / running_max * 100
        ax2.fill_between(dates, 0, dd, color="#ff4444", alpha=0.3)
        ax2.plot(dates, dd, "#cc0000", lw=0.8)
        ax2.axhline(y=-5, color="orange", ls="--", alpha=0.5, lw=0.8)
        ax2.axhline(y=-20, color="red", ls="--", alpha=0.5, lw=0.8)
        ax2.set_ylabel("Drawdown %"); ax2.grid(True, alpha=0.3)
        ax2.annotate("警戒线 -5%", (dates[-1], -5), fontsize=7, color="orange")
        ax2.annotate("清仓线 -20%", (dates[-1], -20), fontsize=7, color="red")

        fig.autofmt_xdate()
        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with col_pie:
        st.subheader("仓位分布")
        position_pie(positions_value, max(0, current_nav - sum(positions_value.values())))

    # ── 第三行：风控规则 ──
    st.divider()
    st.subheader("⚙️ 风控规则")

    rules = [
        ("日亏损 > 5%", "BLOCK_BUY (只平不开)", daily_change < -5),
        ("最大回撤 > 20%", "LIQUIDATE (全部清仓)", abs(current_dd) > 20),
        ("单品种 > 30%", "BLOCK_BUY (限该品种)", any(v / current_nav > 0.3 for v in positions_value.values())),
        ("总仓位 > 80%", "BLOCK_BUY (限所有)", pos_pct > 80),
    ]

    for rule_name, action_desc, triggered in rules:
        col_rule, col_status = st.columns([3, 1])
        with col_rule:
            if triggered:
                st.error(f"🔴 {rule_name} → {action_desc}")
            else:
                st.success(f"🟢 {rule_name} → {action_desc}")
        with col_status:
            st.caption("已触发" if triggered else "未触发")
