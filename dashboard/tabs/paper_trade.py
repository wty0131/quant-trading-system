"""纸交易页 — 并行独立策略 + 自定义组合 + 汇总表"""
import streamlit as st
import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import date, timedelta

from dashboard.components import nav_chart
from execution.paper_runner import (
    STATE_FILE_INDIVIDUAL, STATE_FILE_COMBO,
    IndividualRunner, ComboRunner,
    ALL_STRATEGIES, PAPER_SYMBOLS, seed_all,
)

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _load_individual() -> dict | None:
    if STATE_FILE_INDIVIDUAL.exists():
        with open(STATE_FILE_INDIVIDUAL, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_combo() -> dict | None:
    if STATE_FILE_COMBO.exists():
        with open(STATE_FILE_COMBO, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _show_strategy_detail(name: str, r: dict, cash: float):
    """展示单个策略的持仓/买卖/指标"""
    cols = st.columns(5)
    ret = r.get("total_return", "0%")
    sharpe_val = r.get("sharpe", 0)

    cols[0].metric("净值", f"¥{r.get('nav', 0):,.0f}")
    cols[1].metric("总收益", ret, delta=ret if "+" in str(ret) else None)
    cols[2].metric("Sharpe", f"{sharpe_val:.3f}")
    cols[3].metric("最大回撤", r.get("mdd", "—"))
    cols[4].metric("交易次数", r.get("trade_count", 0))

    # 持仓
    positions = r.get("positions", {})
    if positions:
        with st.expander(f"📦 持仓 ({len(positions)} 只)", expanded=False):
            pos_df = pd.DataFrame([
                {"股票": s, "数量": p["qty"], "成本": f"¥{p['avg_cost']:.2f}"}
                for s, p in sorted(positions.items(), key=lambda x: -x[1]["qty"])[:15]
            ])
            st.dataframe(pos_df, hide_index=True, use_container_width=True)

    # 买卖
    buys = r.get("buys", [])
    sells = r.get("sells", [])
    if buys or sells:
        bcol, scol = st.columns(2)
        with bcol:
            if buys:
                st.caption(f"🟢 最近买入 ({len(buys)}笔)")
                bdf = pd.DataFrame(buys[-5:])
                if not bdf.empty:
                    st.dataframe(bdf[["date","symbol","qty","price"]], hide_index=True, use_container_width=True)
        with scol:
            if sells:
                st.caption(f"🔴 最近卖出 ({len(sells)}笔)")
                sdf = pd.DataFrame(sells[-5:])
                if not sdf.empty:
                    st.dataframe(sdf[["date","symbol","qty","price"]], hide_index=True, use_container_width=True)


def show():
    st.title("🧻 纸交易 — 全A股模拟盘")
    st.caption(f"📡 {len(PAPER_SYMBOLS)} 只A股 | 数据源: baostock 直连 | 100万初始资金")

    cached = _load_individual()

    tab1, tab2 = st.tabs(["📊 PART 1: 独立策略", "🏗 PART 2: 自定义组合"])

    # ═══════════════════════════════════════════
    #  PART 1: 所有策略并行
    # ═══════════════════════════════════════════
    with tab1:
        cash = st.number_input("每个策略的初始资金", 100_000, 100_000_000, 1_000_000, 100_000, key="p1cash")
        col_btn, col_reset = st.columns(2)
        with col_btn:
            run1 = st.button("▶ 运行所有策略 (Part 1)", type="primary", use_container_width=True)
        with col_reset:
            if st.button("🗑 重置 Part 1", type="secondary", use_container_width=True):
                if STATE_FILE_INDIVIDUAL.exists():
                    STATE_FILE_INDIVIDUAL.unlink()
                st.rerun()

        if run1:
            with st.spinner(f"7个策略 × {len(PAPER_SYMBOLS)} 只股票并行回测..."):
                seed_all(cash=cash)
            cached = _load_individual()
            st.success("完成!")
            st.rerun()

        if not cached:
            st.info("👆 点击「运行所有策略」生成种子数据。7个策略各拿全部资金独立运行。")
            return

        reports = cached.get("reports", {})
        if not reports:
            st.info("还没有数据")
            return

        st.caption(f"上次运行: {cached.get('last_date','—')}")

        # 每个策略展开
        for name, r in sorted(reports.items()):
            st.divider()
            st.subheader(f"🔹 {name}")
            _show_strategy_detail(name, r, cash)

        # 净值对比图
        st.divider()
        st.subheader("📈 净值曲线对比")
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2"]
        for (name, r), c in zip(sorted(reports.items()), colors):
            navs = r.get("nav_history", [])
            if navs:
                nv = [float(n) for _, n in navs]
                dt = [t for t, _ in navs]
                ax.plot(dt, np.array(nv) / cash, lw=0.8, color=c, label=f"{name}")
        ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
        ax.legend(ncol=3, fontsize=8)
        ax.set_title("All Strategies — Normalized Net Value", fontweight="bold")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        st.pyplot(fig)
        plt.close(fig)

    # ═══════════════════════════════════════════
    #  PART 2: 自定义组合
    # ═══════════════════════════════════════════
    with tab2:
        col_l, col_r = st.columns([1, 2])
        with col_l:
            st.subheader("⚙️ 构建组合")
            st.caption("选择策略并分配权重")
            selected = {}
            for name in ALL_STRATEGIES:
                cols = st.columns([3, 1])
                with cols[0]:
                    use = st.checkbox(name, value=(name in ["Turtle","Bollinger","RSRS","SVM"]), key=f"cb_{name}")
                with cols[1]:
                    if use:
                        w = st.number_input("%", 0, 100, 25, 5, key=f"wt_{name}", label_visibility="collapsed")
                        selected[name] = w
            if selected:
                total_w = sum(selected.values())
                weights = {n: w / total_w for n, w in selected.items()}
                st.caption(f"总权重: {total_w}%")
                for n, w in weights.items():
                    st.caption(f"  {n}: {w*100:.0f}%")

            cash2 = st.number_input("组合资金", 100_000, 100_000_000, 1_000_000, 100_000, key="p2cash")
            if st.button("▶ 运行组合", type="primary", use_container_width=True, disabled=not selected):
                total_w = sum(selected.values())
                weights = {n: w / total_w for n, w in selected.items()}
                with st.spinner(f"运行 {len(weights)} 策略组合..."):
                    runner = ComboRunner(weights, cash=cash2)
                    report = runner.run()

                    state = {
                        "last_date": str(date.today()),
                        "weights": weights,
                        "cash": cash2,
                        "report": {
                            "nav": report.nav,
                            "total_return": report.total_return,
                            "sharpe": report.sharpe,
                            "mdd": report.mdd,
                            "trade_count": report.trade_count,
                            "positions": report.positions,
                            "buys": report.buys, "sells": report.sells,
                            "nav_history": [
                                (str(t)[:19] if hasattr(t, "isoformat") else str(t), float(n))
                                for t, n in report.nav_history[-252:]
                            ],
                        },
                    }
                    STATE_FILE_COMBO.parent.mkdir(parents=True, exist_ok=True)
                    with open(STATE_FILE_COMBO, "w") as f:
                        json.dump(state, f, indent=2, default=str)
                    st.success("组合回测完成!")
                    st.rerun()

        with col_r:
            combo_state = _load_combo()
            if combo_state:
                cr = combo_state.get("report", {})
                st.subheader(f"🏆 组合报告")
                st.caption(f"权重: {', '.join(f'{k}={float(v)*100:.0f}%' for k,v in combo_state.get('weights', {}).items())}")
                _show_strategy_detail("组合", cr, combo_state.get("cash", 1_000_000))
                if cr.get("nav_history"):
                    nav_chart(cr["nav_history"], "Combo — Net Value")
            else:
                st.info("👈 选择策略并点击「运行组合」")

    # ═══════════════════════════════════════════
    #  底部: 策略汇总表
    # ═══════════════════════════════════════════
    st.divider()
    st.subheader("📊 全策略汇总")

    summary_rows = []

    # Part 1 data
    ind_data = _load_individual()
    if ind_data and ind_data.get("reports"):
        for name, r in sorted(ind_data["reports"].items()):
            summary_rows.append({
                "来源": "独立策略", "策略": name,
                "净值": f"¥{r.get('nav',0):,.0f}",
                "总收益": r.get("total_return", "—"),
                "Sharpe": r.get("sharpe", 0),
                "MDD": r.get("mdd", "—"),
                "交易": r.get("trade_count", 0),
                "胜率": r.get("win_rate", "—"),
                "持仓数": len(r.get("positions", {})),
            })

    # Part 2 data
    combo_data = _load_combo()
    if combo_data and combo_data.get("report"):
        cr = combo_data["report"]
        weights_str = " ".join(f"{k}={float(v)*100:.0f}%" for k, v in combo_data.get("weights", {}).items())
        summary_rows.append({
            "来源": "自定义组合", "策略": f"Combo ({weights_str})",
            "净值": f"¥{cr.get('nav',0):,.0f}",
            "总收益": cr.get("total_return", "—"),
            "Sharpe": cr.get("sharpe", 0),
            "MDD": cr.get("mdd", "—"),
            "交易": cr.get("trade_count", 0),
            "胜率": "—",
            "持仓数": len(cr.get("positions", {})),
        })

    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, use_container_width=True, hide_index=True,
                     column_config={
                         "Sharpe": st.column_config.NumberColumn(format="%.3f"),
                     })
    else:
        st.info("运行 Part 1 或 Part 2 后, 汇总表自动出现")
