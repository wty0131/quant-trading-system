"""纸交易页面 — 每日运行 + 持仓监控 + 净值曲线"""
import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import date

from dashboard.components import nav_chart, position_pie
from data.sources.ashare import AShareSource
from backtest.strategy import DualMAStrategy, BuyAndHoldStrategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy

STATE_FILE = Path("data/paper_state.json")

STRATEGIES = {
    "双均线 (5/20)":  lambda: DualMAStrategy(5, 20),
    "布林带 (20,2)":  lambda: BollingerStrategy(20, 2.0),
    "海龟 (20/10)":    lambda: TurtleStrategy(20, 10, 20, 2.0),
    "RSRS (18,±0.5)": lambda: RSRSStrategy(18, 0.5, -0.5),
}


def _load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def show():
    st.title("🧻 纸交易")
    st.caption("用真实价格模拟交易，不花真金白银。持仓和净值跨天持久化。")

    state = _load_state()

    col_left, col_right = st.columns([2, 1])

    with col_right:
        st.subheader("⚙️ 控制")

        strat_name = st.selectbox("策略", list(STRATEGIES.keys()))
        cash = st.number_input("初始资金", 1000, 100_000_000, 1_000_000, 1000,
                              help="已开仓则不影响当前持仓")

        col1, col2 = st.columns(2)
        with col1:
            run_btn = st.button("▶ 运行今日", type="primary", use_container_width=True)
        with col2:
            if st.button("🗑 重置", type="secondary", use_container_width=True):
                if STATE_FILE.exists():
                    STATE_FILE.unlink()
                state = None
                st.rerun()

        if state:
            st.metric("上次运行", state.get("last_date", "—"))
            st.metric("当前净值", f"¥{state.get('cash', 0) + sum(p.get('quantity',0) * p.get('avg_cost',0) for p in state.get('positions', {}).values()):,.0f}")

    with col_left:
        if run_btn:
            with st.spinner("拉取最新数据 + 运行策略..."):
                from execution.paper_runner import DailyPaperRunner
                runner = DailyPaperRunner(
                    strategy=STRATEGIES[strat_name](),
                    symbols=["sh.000300"],
                    initial_cash=cash,
                )
                report = runner.run()

                # 指标
                cols = st.columns(3)
                cols[0].metric("净值", f"¥{report['nav']:,.0f}")
                cols[1].metric("总收益", report["total_return"])
                cols[2].metric("今日交易", f"{report['trades_today']} 笔")
                state = _load_state()

        # ── 持仓 + 净值 ──
        if state and state.get("nav_history"):
            st.divider()
            navs = [(t if isinstance(t, str) else str(t), float(n))
                    for t, n in state["nav_history"]]
            nav_chart(navs, "Paper Trading — Net Value")

            # 持仓饼图
            positions = state.get("positions", {})
            cash = state.get("cash", 0)
            st.divider()
            st.subheader("当前持仓")

            cols2 = st.columns(2)
            with cols2[0]:
                if positions:
                    pos_df = pd.DataFrame([
                        {"品种": s, "数量": p["quantity"], "均价": f"¥{p['avg_cost']:.2f}"}
                        for s, p in positions.items()
                    ])
                    st.dataframe(pos_df, hide_index=True, use_container_width=True)
                else:
                    st.info("当前空仓")

            with cols2[1]:
                pos_values = {}
                latest_price = 3500  # 默认，实际应由最新bar提供
                for sym, p in positions.items():
                    pos_values[sym] = p["quantity"] * latest_price
                position_pie(pos_values, cash, "Portfolio")

            # 最近交易
            trades = state.get("trades", [])
            if trades:
                st.divider()
                st.subheader("最近交易")
                trades_df = pd.DataFrame(trades[-10:])
                if "timestamp" in trades_df.columns:
                    trades_df = trades_df[["timestamp", "symbol", "direction", "price", "quantity", "commission"]]
                st.dataframe(trades_df, hide_index=True, use_container_width=True)
        elif not state:
            st.info("👆 点击「运行今日」开始纸交易。净值曲线和持仓会在首次运行后显示。")
