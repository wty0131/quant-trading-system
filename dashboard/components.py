"""复用组件 — 净值图、指标卡、持仓表"""
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def metric_card(label: str, value: str, delta: str = None, color: str = None):
    """指标卡"""
    delta_color = "normal"
    if delta and "▲" in delta:
        delta_color = "normal"
    elif delta and "▼" in delta:
        delta_color = "inverse"
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def nav_chart(nav_history: list[tuple], title: str = "Net Value", height: int = 400):
    """净值曲线 (用 matplotlib 渲染)"""
    if not nav_history:
        st.info("暂无数据")
        return

    dates = [t for t, _ in nav_history]
    navs = np.array([n for _, n in nav_history])

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, navs / navs[0], "steelblue", lw=1.5)
    ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
    ax.fill_between(dates, 1, navs / navs[0], where=(navs / navs[0] >= 1),
                    color="red", alpha=0.08)
    ax.fill_between(dates, navs / navs[0], 1, where=(navs / navs[0] < 1),
                    color="green", alpha=0.08)
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel("Net Value (normalized)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    st.pyplot(fig)
    plt.close(fig)


def drawdown_chart(nav_history: list[tuple], height: int = 250):
    """回撤曲线"""
    if not nav_history:
        return

    dates = [t for t, _ in nav_history]
    navs = np.array([n for _, n in nav_history])
    running_max = np.maximum.accumulate(navs)
    dd = (navs - running_max) / running_max * 100

    fig, ax = plt.subplots(figsize=(10, 2.5))
    ax.fill_between(dates, 0, dd, color="#ff4444", alpha=0.3)
    ax.plot(dates, dd, "#cc0000", lw=0.8)
    ax.set_ylabel("Drawdown %")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    st.pyplot(fig)
    plt.close(fig)


def position_pie(positions: dict[str, float], cash: float, title: str = "Portfolio"):
    """持仓饼图"""
    total = cash + sum(positions.values())
    labels = list(positions.keys()) + ["Cash"]
    values = list(positions.values()) + [cash]

    fig, ax = plt.subplots(figsize=(5, 5))
    colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=colors, startangle=90,
    )
    ax.set_title(title, fontweight="bold")
    st.pyplot(fig)
    plt.close(fig)


def report_table(report):
    """绩效报告表格"""
    cols = st.columns(4)
    cols[0].metric("Total Return", f"{report.total_return*100:.2f}%")
    cols[1].metric("Sharpe", f"{report.sharpe_ratio:.3f}")
    cols[2].metric("Max DD", f"{report.max_drawdown*100:.2f}%")
    cols[3].metric("Calmar", f"{report.calmar_ratio:.3f}")

    cols2 = st.columns(4)
    cols2[0].metric("Annual Vol", f"{report.annual_volatility*100:.1f}%")
    cols2[1].metric("Win Rate", f"{report.win_rate*100:.1f}%")
    cols2[2].metric("Trades", str(report.total_trades))
    cols2[3].metric("Profit Factor", f"{report.profit_factor:.2f}")


def trades_table(trades: list[dict]):
    """交易明细表"""
    if not trades:
        st.info("暂无交易记录")
        return
    df = pd.DataFrame(trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp", ascending=False).head(20)
    st.dataframe(df[["timestamp", "symbol", "direction", "price", "quantity", "commission"]],
                 use_container_width=True)
