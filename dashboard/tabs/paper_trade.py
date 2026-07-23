"""纸交易页 — 独立策略+组合+历史+基准+导出"""
import streamlit as st
import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from pathlib import Path

from dashboard.components import nav_chart, export_csv
from execution.paper_runner import (
    STATE_FILE_INDIVIDUAL, STATE_FILE_COMBO, IndividualRunner,
    ALL_STRATEGIES, _get_symbols, seed_all,
)
from data.ashare_pool import fetch_all_stocks
from data.cache import CachedFetcher
from datetime import date

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _load_individual():
    if STATE_FILE_INDIVIDUAL.exists():
        with open(STATE_FILE_INDIVIDUAL, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_combo():
    if STATE_FILE_COMBO.exists():
        with open(STATE_FILE_COMBO, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_history():
    """历史快照列表"""
    from execution.paper_runner import HISTORY_DIR
    if not HISTORY_DIR.exists():
        return []
    snaps = []
    for fp in sorted(HISTORY_DIR.glob("paper_*.json")):
        with open(fp, "r", encoding="utf-8") as f:
            snaps.append(json.load(f))
    return snaps


def show():
    st.title("🧻 纸交易 — 全A股模拟盘")
    syms = _get_symbols()
    st.caption(f"📡 {len(syms)} 只A股(全市场) | 缓存加速 | 基准对比 | 历史回溯")

    cached = _load_individual()

    tab1, tab2, tab3 = st.tabs(["📊 PART 1: 独立策略", "🏗 PART 2: 自定义组合", "📜 历史记录"])

    # ═══════════════ PART 1 ═══════════════
    with tab1:
        cash = st.number_input("每个策略初始资金", 100_000, 100_000_000, 1_000_000, 100_000, key="p1cash")
        col_btn, col_reset, col_prefetch = st.columns(3)
        with col_btn:
            run1 = st.button("▶ 运行所有策略", type="primary", use_container_width=True)
        with col_reset:
            if st.button("🗑 重置", type="secondary", use_container_width=True):
                if STATE_FILE_INDIVIDUAL.exists():
                    STATE_FILE_INDIVIDUAL.unlink()
                st.rerun()
        with col_prefetch:
            if st.button("🔥 预热缓存", type="secondary", use_container_width=True, help="一次性拉全部5000只股票数据存SQLite，之后秒开"):
                with st.spinner(f"预热 {len(syms)} 只股票数据..."):
                    cache = CachedFetcher()
                    cache.prefetch_all(syms)
                st.success("缓存预热完成!")
                st.rerun()

        if run1:
            with st.spinner(f"10个策略 × {len(syms)} 只股票并行 (缓存加速)..."):
                seed_all(cash=cash)
            cached = _load_individual()
            st.success("完成! 历史快照已保存")
            st.rerun()

        if not cached:
            st.info("👆 点「预热缓存」一次性下载数据 → 再点「运行所有策略」。之后每天只需几分钟增量更新。")
            return

        reports = cached.get("reports", {})
        if not reports:
            st.info("还没有数据")
            return

        st.caption(f"上次运行: {cached.get('last_date', '—')}")

        for name, r in sorted(reports.items()):
            st.divider()
            st.subheader(f"🔹 {name}")

            cols = st.columns(5)
            cols[0].metric("净值", f"¥{r.get('nav',0):,.0f}")
            cols[1].metric("总收益", r.get("total_return","-"))
            cols[2].metric("Sharpe", f"{r.get('sharpe',0):.3f}")
            cols[3].metric("MDD", r.get("mdd","-"))
            cols[4].metric("vs 沪深300", r.get("bench_return","-"))

            positions = r.get("positions", {})
            if positions:
                with st.expander(f"📦 持仓 ({len(positions)} 只)", expanded=False):
                    pos_df = pd.DataFrame([
                        {"股票": s, "数量": p["qty"], "成本": f"¥{p['avg_cost']:.2f}"}
                        for s, p in sorted(positions.items(), key=lambda x: -x[1]["qty"])[:15]
                    ])
                    st.dataframe(pos_df, hide_index=True, use_container_width=True)

            buys = r.get("buys", [])
            sells = r.get("sells", [])
            if buys or sells:
                bcol, scol = st.columns(2)
                with bcol:
                    if buys:
                        st.caption(f"🟢 最近买入 ({len(buys)}笔)")
                        st.dataframe(pd.DataFrame(buys[-5:])[["date","symbol","qty","price"]],
                                    hide_index=True, use_container_width=True)
                with scol:
                    if sells:
                        st.caption(f"🔴 最近卖出 ({len(sells)}笔)")
                        st.dataframe(pd.DataFrame(sells[-5:])[["date","symbol","qty","price"]],
                                    hide_index=True, use_container_width=True)

        # 净值对比图
        st.divider()
        st.subheader("📈 净值曲线对比")
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"]
        for (name, r), c in zip(sorted(reports.items()), colors):
            navs = r.get("nav_history", [])
            if navs:
                nv = [float(n) for _, n in navs]
                dt = [t for t, _ in navs]
                ax.plot(dt, np.array(nv) / cash, lw=0.8, color=c, label=name)
        ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
        ax.legend(ncol=3, fontsize=7)
        ax.set_title("All Strategies — Normalized", fontweight="bold")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        st.pyplot(fig)
        plt.close(fig)

        # 导出
        st.divider()
        export_rows = []
        for n, r in sorted(reports.items()):
            export_rows.append({
                "策略": n, "净值": round(r.get("nav",0),0),
                "总收益": r.get("total_return","-"),
                "Sharpe": r.get("sharpe",0), "MDD": r.get("mdd","-"),
                "vs沪深300": r.get("bench_return","-"),
                "交易": r.get("trade_count",0), "持仓数": len(r.get("positions",{})),
            })
        export_csv(export_rows, "paper_individual")

    # ═══════════════ PART 2 ═══════════════
    with tab2:
        col_l, col_r = st.columns([1, 2])
        with col_l:
            st.subheader("⚙️ 构建组合")
            selected = {}
            for name in ALL_STRATEGIES:
                cols = st.columns([3, 1])
                with cols[0]:
                    use = st.checkbox(name, value=(name in ["Turtle","Bollinger","RSRS","SVM"]), key=f"cb2_{name}")
                with cols[1]:
                    if use:
                        w = st.number_input("%", 0, 100, 25, 5, key=f"wt2_{name}", label_visibility="collapsed")
                        selected[name] = w
            if selected:
                total_w = sum(selected.values())
                weights = {n: w / total_w for n, w in selected.items()}
                for n, w in weights.items():
                    st.caption(f"  {n}: {w*100:.0f}%")

            cash2 = st.number_input("组合资金", 100_000, 100_000_000, 1_000_000, 100_000, key="p2cash")
            if st.button("▶ 运行组合", type="primary", use_container_width=True, disabled=not selected):
                total_w = sum(selected.values())
                weights = {n: w / total_w for n, w in selected.items()}
                from execution.paper_runner import ComboRunner
                with st.spinner("运行组合..."):
                    runner = ComboRunner(weights, cash=cash2)
                    report = runner.run()
                    state = {
                        "last_date": str(date.today()),
                        "weights": weights, "cash": cash2,
                        "report": {
                            "nav": report.nav, "total_return": report.total_return,
                            "sharpe": report.sharpe, "mdd": report.mdd,
                            "trade_count": report.trade_count,
                            "positions": report.positions,
                            "buys": report.buys, "sells": report.sells,
                            "nav_history": [(str(t)[:19], float(n)) for t, n in report.nav_history[-252:]],
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
                _show_combo_report(cr, combo_state)
                if cr.get("nav_history"):
                    nav_chart(cr["nav_history"], "Combo — Net Value")
            else:
                st.info("👈 勾选策略 → 调权重 → 点击「运行组合」")

    # ═══════════════ PART 3: 历史记录 ═══════════════
    with tab3:
        st.subheader("📜 历史快照")
        snaps = _load_history()
        if not snaps:
            st.info("还没有历史快照。运行一次纸交易后自动保存。")
        else:
            st.caption(f"共 {len(snaps)} 条快照")
            for snap in reversed(snaps[-10:]):
                ts = snap.get("timestamp", snap.get("last_date", "—"))[:19]
                with st.expander(f"📸 {ts}"):
                    reports = snap.get("reports", {})
                    rows = []
                    for n, r in sorted(reports.items()):
                        rows.append({
                            "策略": n, "净值": f"¥{r.get('nav',0):,.0f}",
                            "总收益": r.get("total_return","-"), "Sharpe": r.get("sharpe",0),
                            "MDD": r.get("mdd","-"), "vs沪深300": r.get("bench_return","-"),
                        })
                    if rows:
                        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ═══════════════ 底部汇总表 ═══════════════
    st.divider()
    st.subheader("📊 全策略汇总")
    summary_rows = []
    ind_data = _load_individual()
    if ind_data and ind_data.get("reports"):
        for n, r in sorted(ind_data["reports"].items()):
            summary_rows.append({
                "来源": "独立", "策略": n,
                "净值": f"¥{r.get('nav',0):,.0f}",
                "总收益": r.get("total_return","-"),
                "Sharpe": r.get("sharpe",0), "MDD": r.get("mdd","-"),
                "vs沪深300": r.get("bench_return","-"),
                "交易": r.get("trade_count",0),
                "持仓数": len(r.get("positions",{})),
            })
    combo_data = _load_combo()
    if combo_data and combo_data.get("report"):
        cr = combo_data["report"]
        w_str = " ".join(f"{k}={float(v)*100:.0f}%" for k, v in combo_data.get("weights", {}).items())
        summary_rows.append({
            "来源": "组合", "策略": f"Combo ({w_str})",
            "净值": f"¥{cr.get('nav',0):,.0f}",
            "总收益": cr.get("total_return","-"),
            "Sharpe": cr.get("sharpe",0), "MDD": cr.get("mdd","-"),
            "vs沪深300": "—", "交易": cr.get("trade_count",0),
            "持仓数": len(cr.get("positions",{})),
        })
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        export_csv(summary_rows, "paper_summary")
    else:
        st.info("运行 Part 1 或 Part 2 后, 汇总表自动出现")


def _show_combo_report(cr: dict, cs: dict):
    cols = st.columns(4)
    cols[0].metric("净值", f"¥{cr.get('nav',0):,.0f}")
    cols[1].metric("总收益", cr.get("total_return","-"))
    cols[2].metric("Sharpe", f"{cr.get('sharpe',0):.3f}")
    cols[3].metric("MDD", cr.get("mdd","-"))

    weights = cs.get("weights", {})
    st.caption(f"权重: {', '.join(f'{k}={float(v)*100:.0f}%' for k,v in weights.items())}")

    positions = cr.get("positions", {})
    if positions:
        with st.expander(f"📦 持仓 ({len(positions)} 只)", expanded=False):
            pos_df = pd.DataFrame([
                {"名称": s, "数量": p["qty"], "成本": f"¥{p.get('avg_cost',0):.2f}"}
                for s, p in sorted(positions.items(), key=lambda x: -x[1]["qty"])[:15]
            ])
            st.dataframe(pos_df, hide_index=True, use_container_width=True)

    buys = cr.get("buys", [])
    sells = cr.get("sells", [])
    if buys or sells:
        bcol, scol = st.columns(2)
        with bcol:
            if buys:
                st.caption(f"🟢 最近买入 ({len(buys)}笔)")
                st.dataframe(pd.DataFrame(buys[-5:])[["date","symbol","qty","price"]],
                            hide_index=True, use_container_width=True)
        with scol:
            if sells:
                st.caption(f"🔴 最近卖出 ({len(sells)}笔)")
                st.dataframe(pd.DataFrame(sells[-5:])[["date","symbol","qty","price"]],
                            hide_index=True, use_container_width=True)
