"""总览页 — 净值曲线 + 持仓 + 交易记录"""
import streamlit as st
import pandas as pd
import numpy as np

from dashboard.components import nav_chart, drawdown_chart, position_pie, trades_table, metric_card
from data.store import DataStore
from backtest.engine import BacktestEngine
from backtest.strategy import BuyAndHoldStrategy


@st.cache_data(ttl=3600)
def load_overview_data():
    """加载总览数据 (缓存在内存1小时)"""
    store = DataStore("data/quant.db")

    # 尝试加载 A股 数据，优先用已有数据
    df = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01")
    if df.empty:
        from data.sources.ashare import AShareSource
        ashare = AShareSource()
        df = ashare.get_history(["sh.000300", "sh.600519"], "2024-01-01", "2024-12-31")
        store.save(df, "ashare", "daily")
        df = df[df["symbol"] == "sh.000300"]

    # 跑一个买入持有作为基准净值
    engine = BacktestEngine(df, BuyAndHoldStrategy(), 1_000_000, slippage=0.001, commission_rate=0.0003)
    report = engine.run()

    return df, report


def show():
    st.title("📊 总览仪表盘")
    st.caption("基于真实历史数据的回测快照")

    with st.spinner("加载数据中..."):
        df, report = load_overview_data()

    # ── 第一行：关键指标 ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("当前净值", f"¥{report.final_nav:,.0f}")
    with c2:
        total_ret = report.total_return * 100
        delta = f"{'▲' if total_ret > 0 else '▼'} {abs(total_ret):.2f}%"
        metric_card("总收益", f"{total_ret:.2f}%", delta)
    with c3:
        metric_card("夏普比率", f"{report.sharpe_ratio:.3f}")
    with c4:
        mdd = report.max_drawdown * 100
        metric_card("最大回撤", f"{mdd:.2f}%")

    # ── 第二行：净值曲线 ──
    st.divider()
    st.subheader("净值曲线")

    col_left, col_right = st.columns([3, 1])
    with col_left:
        nav_chart(report.nav_history, "Benchmark Net Value (Buy & Hold)", height=350)
    with col_right:
        # 简易持仓饼图
        if report.nav_history:
            last_nav = report.nav_history[-1][1]
            pos_value = max(0, last_nav - 1_000_000)
            position_pie({"沪深300": pos_value}, max(0, 1_000_000 - pos_value + 1e6 * 0.1))
        st.caption(f"总天数: {report.total_days}")

    # ── 第三行：回撤 + 交易 ──
    st.divider()
    st.subheader("回撤曲线")
    drawdown_chart(report.nav_history)

    # 最新数据预览
    st.divider()
    st.subheader("最新数据 (最近10日)")
    st.dataframe(
        df.sort_values("date").tail(10)[["date", "open", "high", "low", "close", "volume"]],
        use_container_width=True,
        hide_index=True,
    )
