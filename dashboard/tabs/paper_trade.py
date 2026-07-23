"""多策略组合纸交易页面 — 净值 + 权重 + 持仓"""
import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path

from dashboard.components import nav_chart
from execution.paper_runner import (
    STATE_FILE, ComboPaperRunner, COMBO_STRATEGIES, PAPER_SYMBOLS,
)

STOCK_NAMES = {
    "sz.000725": "京东方A",
    "sh.600050": "中国联通",
    "sh.601668": "中国建筑",
    "sh.601398": "工商银行",
}


def _load_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def show():
    st.title("🧻 纸交易 — 多策略组合")
    st.caption("Turtle + Bollinger + RSRS + SVM — 4个低相关策略按波动率倒数分配权重")

    state = _load_state()

    col_left, col_right = st.columns([2, 1])

    with col_right:
        st.subheader("⚙️ 控制")
        st.info(
            f"**模拟盘股票池:**\n"
            f"• {STOCK_NAMES['sz.000725']} 约3元 (面板)\n"
            f"• {STOCK_NAMES['sh.600050']} 约5元 (通信)\n"
            f"• {STOCK_NAMES['sh.601668']} 约5元 (基建)\n"
            f"• {STOCK_NAMES['sh.601398']} 约5元 (银行)\n\n"
            f"**组合逻辑:**\n"
            f"① 去重: 相关>0.7只留一个\n"
            f"② 配权: 波动率倒数\n"
            f"③ 再平衡: 每20天\n\n"
            f"Turtle+Bollinger+RSRS+SVM"
        )

        cash = st.number_input("初始资金", 1000, 100_000_000, 2000, 100)

        col1, col2 = st.columns(2)
        with col1:
            run_btn = st.button("▶ 运行今日", type="primary", use_container_width=True)
        with col2:
            if st.button("🗑 重置", type="secondary", use_container_width=True):
                if STATE_FILE.exists():
                    STATE_FILE.unlink()
                st.rerun()

        if state:
            last_nav = state["nav_history"][-1][1] if state["nav_history"] else cash
            st.metric("上次运行", state.get("last_date", "—"))
            st.metric("当前净值", f"¥{float(last_nav):,.0f}")

            st.divider()
            st.subheader("策略权重")
            weights = state.get("weights", {})
            for name, w in weights.items():
                st.metric(name, w if isinstance(w, str) else f"{float(w)*100:.0f}%")

    with col_left:
        if run_btn:
            with st.spinner("拉取数据 + 4策略运行..."):
                runner = ComboPaperRunner(
                    strategies=COMBO_STRATEGIES,
                    symbols=PAPER_SYMBOLS,
                    initial_cash=cash,
                )
                report = runner.run()

                cols = st.columns(3)
                cols[0].metric("组合净值", f"¥{report['nav']:,.0f}")
                cols[1].metric("总收益", report["total_return"])
                cols[2].metric("策略数", f"{len(COMBO_STRATEGIES)} 个")
                state = _load_state()
                st.success(f"完成! 权重: {', '.join(report['weights'].values())}")

        if state and state.get("nav_history"):
            st.divider()
            st.subheader("组合净值曲线")
            navs = [(t if isinstance(t, str) else str(t), float(n))
                    for t, n in state["nav_history"]]
            nav_chart(navs, "Multi-Strategy Combo — Net Value")

            # 策略详情
            st.divider()
            st.subheader("各策略持仓")
            broker_states = state.get("broker_states", {})
            if broker_states:
                rows = []
                for name, bs in broker_states.items():
                    pos_str = ", ".join(
                        f"{s}({p['qty']}股)"
                        for s, p in bs.get("positions", {}).items()
                    ) or "空仓"
                    rows.append({
                        "策略": name,
                        "现金": f"¥{bs.get('cash', 0):,.0f}",
                        "持仓": pos_str,
                        "权重": state.get("weights", {}).get(name, "—"),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            st.divider()
            st.caption(f"状态文件: {STATE_FILE}")
            st.caption(f"净值记录: {len(state['nav_history'])} 条")

        elif not state:
            st.info("👆 点击「运行今日」开始。四个策略会自动按波动率倒数分配权重。")
