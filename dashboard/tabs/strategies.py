"""策略页 — 全部策略对比 + 相关性矩阵"""
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from data.store import DataStore
from backtest.engine import BacktestEngine
from backtest.strategy import BuyAndHoldStrategy, DualMAStrategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy
from strategies.multifactor import MultiFactorStrategy
from strategies.pairs import PairsStrategy
from strategies.qmt_svm import QMTSVMStrategy
from strategies.qmt_arima import QMTARIMAStrategy
from strategies.qmt_index_ma import QMTIndexMAStrategy
from risk.combiner import StrategyCombiner
from risk.allocator import InvVolAllocator, EqualAllocator


@st.cache_data(ttl=7200)
def run_all_strategies(symbol="sh.000300"):
    """跑全部策略并缓存结果"""
    store = DataStore("data/quant.db")
    df = store.load("ashare", "daily", symbols=[symbol], start="2024-01-01")
    if df.empty:
        from data.sources.ashare import AShareSource
        ashare = AShareSource()
        df = ashare.get_history([symbol], "2024-01-01", "2024-12-31")
        store.save(df, "ashare", "daily")

    # ── 全部 10 个策略 ──
    strategies = {
        "① Buy&Hold (基准)":    BuyAndHoldStrategy(),
        "② DualMA (5/20)":      DualMAStrategy(5, 20),
        "③ Bollinger (20,2)":   BollingerStrategy(20, 2.0),
        "④ Turtle (20/10)":      TurtleStrategy(20, 10, 20, 2.0),
        "⑤ RSRS (18,±0.5)":     RSRSStrategy(18, 0.5, -0.5),
        "⑥ MultiFactor (top5)": MultiFactorStrategy(top_k=5),
        "⑦ Pairs (Z±2)":        PairsStrategy(60, 2.0, 0.0),
        "⑧ QMT SVM (120d)":     QMTSVMStrategy(train_days=120, retrain_freq=20),
        "⑨ QMT ARIMA (2,1,2)":  QMTARIMAStrategy(history=120, refit_freq=5),
        "⑩ QMT 上证50 MA":      QMTIndexMAStrategy("上证50", 5, 20),
    }

    reports = {}
    daily_rets = {}
    errors = {}

    progress = st.progress(0, "运行中...")
    total = len(strategies)
    for i, (name, strat) in enumerate(strategies.items()):
        progress.progress((i + 1) / total, f"回测: {name}")
        try:
            engine = BacktestEngine(df, strat, 1_000_000, 0.001, 0.0003)
            r = engine.run()
            reports[name] = r
            navs = np.array([n for _, n in r.nav_history])
            if len(navs) > 1:
                daily_rets[name] = np.diff(navs) / navs[:-1]
        except Exception as e:
            errors[name] = str(e)[:80]
    progress.empty()

    # 组合（只用产生收益数据的策略）
    if daily_rets:
        combiner = StrategyCombiner(
            {k: strategies[k] for k in daily_rets if k in strategies},
            InvVolAllocator(), 1_000_000,
        )
        try:
            combo_report = combiner.run(df)
            corr_matrix = combiner.get_correlation_matrix()
        except Exception:
            combo_report = None
            corr_matrix = pd.DataFrame()
    else:
        combo_report = None
        corr_matrix = pd.DataFrame()

    return df, reports, daily_rets, combo_report, corr_matrix, errors


def show():
    st.title("全部策略对比")
    st.caption("10个策略在同一数据上的回测对比 — 系统全策略一览")

    with st.spinner("正在计算所有策略回测..."):
        df, reports, daily_rets, combo_report, corr_matrix, errors = run_all_strategies()

    if errors:
        with st.expander(f"⚠ {len(errors)} 个策略异常（点击展开）"):
            for name, err in errors.items():
                st.caption(f"{name}: {err}")

    # ── 汇总表 ──
    st.subheader("绩效汇总")
    rows = []
    for name, r in sorted(reports.items()):
        rows.append({
            "策略": name,
            "收益": f"{r.total_return*100:.2f}%",
            "Sharpe": f"{r.sharpe_ratio:.3f}",
            "MDD": f"{r.max_drawdown*100:.2f}%",
            "Calmar": f"{r.calmar_ratio:.3f}",
            "交易": r.total_trades,
            "胜率": f"{r.win_rate*100:.0f}%" if r.total_trades > 0 else "—",
            "盈亏比": f"{r.profit_factor:.2f}" if r.total_trades > 0 else "—",
        })

    if combo_report is not None:
        rows.append({
            "策略": "\U0001F3C6 组合 (InvVol)",
            "收益": f"{combo_report.total_return*100:.2f}%",
            "Sharpe": f"{combo_report.sharpe_ratio:.3f}",
            "MDD": f"{combo_report.max_drawdown*100:.2f}%",
            "Calmar": f"{combo_report.calmar_ratio:.3f}",
            "交易": "—", "胜率": "—", "盈亏比": "—",
        })

    df_table = pd.DataFrame(rows)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # ── 净值对比图 (所有策略) ──
    st.divider()
    st.subheader("净值曲线全景对比")

    n = len(reports)
    tab10_colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    fig, ax = plt.subplots(figsize=(12, 6))
    for (name, r), color in zip(reports.items(), tab10_colors[:n]):
        navs = np.array([n for _, n in r.nav_history])
        dates = [t for t, _ in r.nav_history]
        ax.plot(dates, navs / 1_000_000, lw=0.8, color=color, alpha=0.8, label=name)

    if combo_report is not None:
        combo_navs = np.array([n for _, n in combo_report.nav_history])
        combo_dates = [t for t, _ in combo_report.nav_history]
        ax.plot(combo_dates, combo_navs / 1_000_000, "k", lw=2.5, label="COMBO")

    ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
    ax.legend(ncol=2, fontsize=7, loc="upper left")
    ax.set_title(f"All {n} Strategies + Combo (CSI 300, 2024)", fontweight="bold")
    ax.set_ylabel("Net Value")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    st.pyplot(fig)
    plt.close(fig)

    # ── 回撤对比 ──
    st.subheader("回撤曲线对比")
    fig2, ax2 = plt.subplots(figsize=(12, 4))
    for (name, r), color in zip(reports.items(), tab10_colors[:n]):
        navs = np.array([n for _, n in r.nav_history])
        if len(navs) < 2:
            continue
        running_max = np.maximum.accumulate(navs)
        dd = (navs - running_max) / running_max * 100
        dates = [t for t, _ in r.nav_history]
        ax2.plot(dates, dd, lw=0.6, color=color, alpha=0.7, label=name)

    ax2.axhline(y=-5, color="orange", ls="--", alpha=0.4, lw=0.8)
    ax2.set_ylabel("Drawdown %")
    ax2.set_xlabel("Date")
    ax2.legend(ncol=2, fontsize=7, loc="lower left")
    ax2.grid(True, alpha=0.3)
    fig2.autofmt_xdate()
    st.pyplot(fig2)
    plt.close(fig2)

    # ── 相关性矩阵 ──
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("策略日收益相关性")
        if not corr_matrix.empty:
            fig3, ax3 = plt.subplots(figsize=(6, 6))
            # 用短名
            short_names = {k: k.split("(")[0].strip() for k in corr_matrix.columns}
            labels = [short_names.get(c, c) for c in corr_matrix.columns]
            im = ax3.imshow(corr_matrix, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
            ax3.set_xticks(range(len(labels)))
            ax3.set_yticks(range(len(labels)))
            ax3.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
            ax3.set_yticklabels(labels, fontsize=7)
            for i in range(len(labels)):
                for j in range(len(labels)):
                    val = corr_matrix.iloc[i, j]
                    ax3.text(j, i, f"{val:.2f}", ha="center", va="center",
                             fontsize=6, color="white" if abs(val) > 0.4 else "black")
            ax3.set_title("Strategy Return Correlation", fontweight="bold", fontsize=10)
            plt.colorbar(im, shrink=0.8)
            st.pyplot(fig3)
            plt.close(fig3)

    with col2:
        st.subheader("组合资金分配 (InvVol)")
        st.markdown("""
        **波动率倒数加权** — 最稳健的方法:
        - 高波动策略 → 分得少
        - 低波动策略 → 分得多
        - 只依赖波动率持续性(可预测)
        - 不碰收益预测(不可预测)

        **三个分配方法对比:**
        | 方法 | 可靠性 | 输入 |
        |------|--------|------|
        | 等权 | 基准线 | 无 |
        | InvVol | 最稳健 | 波动率 |
        | Max Sharpe | 易过拟合 | 收益+协方差 |
        """)

    # ── 组合绩效 ──
    if combo_report is not None:
        st.divider()
        st.subheader("组合绩效")
        valid_sharpes = [r.sharpe_ratio for r in reports.values() if not np.isnan(r.sharpe_ratio)]
        avg_sharpe = np.mean(valid_sharpes) if valid_sharpes else 0
        cols = st.columns(4)
        cols[0].metric("组合 Sharpe", f"{combo_report.sharpe_ratio:.3f}",
                       delta=f"{combo_report.sharpe_ratio - avg_sharpe:.3f} vs 均值")
        cols[1].metric("组合 MDD", f"{combo_report.max_drawdown*100:.2f}%")
        cols[2].metric("组合收益", f"{combo_report.total_return*100:.2f}%")
        cols[3].metric("组合波动", f"{combo_report.annual_volatility*100:.1f}%")
