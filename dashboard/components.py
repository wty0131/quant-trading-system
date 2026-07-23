"""复用组件 — 净值图、指标卡、持仓表、导出"""
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
from datetime import datetime

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def metric_card(label: str, value: str, delta: str = None):
    st.metric(label=label, value=value, delta=delta)


def nav_chart(nav_history: list[tuple], title: str = "Net Value",
              bench_history: list[tuple] = None, height: int = 400):
    if not nav_history:
        st.info("暂无数据")
        return
    dates = [t for t, _ in nav_history]
    navs = np.array([n for _, n in nav_history])
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, navs / navs[0], "steelblue", lw=1.5, label="Strategy")
    if bench_history and len(bench_history) > 0:
        b_dates = [t for t, _ in bench_history]
        b_navs = np.array([n for _, n in bench_history])
        if len(b_navs) > 1:
            ax.plot(b_dates, b_navs / b_navs[0], "gray", lw=1, ls="--", alpha=0.6, label="CSI 300")
    ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
    ax.fill_between(dates, 1, navs / navs[0], where=(navs / navs[0] >= 1),
                    color="red", alpha=0.08)
    ax.fill_between(dates, navs / navs[0], 1, where=(navs / navs[0] < 1),
                    color="green", alpha=0.08)
    ax.set_title(title, fontweight="bold")
    ax.set_ylabel("Normalized")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    st.pyplot(fig)
    plt.close(fig)


def drawdown_chart(nav_history: list[tuple]):
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


def report_table(report):
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


def export_csv(data: list[dict], filename_prefix: str):
    """导出按钮"""
    if not data:
        return
    df = pd.DataFrame(data)
    csv = df.to_csv(index=False)
    st.download_button(
        label=f"📥 下载 {filename_prefix}.csv",
        data=csv,
        file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
