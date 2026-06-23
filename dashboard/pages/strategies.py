"""策略页 — 多策略对比 + 相关性矩阵"""
import streamlit as st
import pandas as pd
import numpy as np

from dashboard.components import nav_chart, drawdown_chart
from data.store import DataStore
from backtest.engine import BacktestEngine
from backtest.strategy import DualMAStrategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy
from risk.combiner import StrategyCombiner
from risk.allocator import InvVolAllocator, EqualAllocator


@st.cache_data(ttl=7200)
def run_all_strategies(symbol="sh.000300"):
    """跑所有策略并缓存结果"""
    store = DataStore("data/quant.db")
    df = store.load("ashare", "daily", symbols=[symbol], start="2024-01-01")
    if df.empty:
        from data.sources.ashare import AShareSource
        ashare = AShareSource()
        df = ashare.get_history([symbol], "2024-01-01", "2024-12-31")
        store.save(df, "ashare", "daily")

    strategies = {
        "DualMA (5/20)": DualMAStrategy(5, 20),
        "Bollinger (20,2)": BollingerStrategy(20, 2.0),
        "Turtle (20/10)": TurtleStrategy(20, 10, 20, 2.0),
        "RSRS (18,0.5,-0.5)": RSRSStrategy(18, 0.5, -0.5),
    }

    reports = {}
    daily_rets = {}

    for name, strat in strategies.items():
        engine = BacktestEngine(df, strat, 1_000_000, 0.001, 0.0003)
        r = engine.run()
        reports[name] = r
        navs = np.array([n for _, n in r.nav_history])
        if len(navs) > 1:
            daily_rets[name] = np.diff(navs) / navs[:-1]

    # 组合
    combiner = StrategyCombiner(strategies, InvVolAllocator(), 1_000_000)
    combo_report = combiner.run(df)
    corr_matrix = combiner.get_correlation_matrix()

    return df, reports, daily_rets, combo_report, corr_matrix


def show():
    st.title("📈 策略对比")

    with st.spinner("正在计算所有策略回测..."):
        df, reports, daily_rets, combo_report, corr_matrix = run_all_strategies()

    # ── 汇总表 ──
    st.subheader("📊 绩效对比")
    rows = []
    for name, r in reports.items():
        rows.append({
            "策略": name, "收益": f"{r.total_return*100:.2f}%",
            "Sharpe": f"{r.sharpe_ratio:.3f}", "MDD": f"{r.max_drawdown*100:.2f}%",
            "Calmar": f"{r.calmar_ratio:.3f}", "交易": r.total_trades,
            "胜率": f"{r.win_rate*100:.0f}%", "盈亏比": f"{r.profit_factor:.2f}",
        })

    # 加组合行
    rows.append({
        "策略": "🏆 组合 (InvVol)", "收益": f"{combo_report.total_return*100:.2f}%",
        "Sharpe": f"{combo_report.sharpe_ratio:.3f}", "MDD": f"{combo_report.max_drawdown*100:.2f}%",
        "Calmar": f"{combo_report.calmar_ratio:.3f}", "交易": "-",
        "胜率": "-", "盈亏比": "-",
    })

    df_table = pd.DataFrame(rows)
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # ── 净值对比图 ──
    st.divider()
    st.subheader("📈 净值曲线对比")

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["steelblue", "orange", "green", "purple"]
    for (name, r), color in zip(reports.items(), colors):
        navs = np.array([n for _, n in r.nav_history])
        dates = [t for t, _ in r.nav_history]
        ax.plot(dates, navs / 1_000_000, lw=1, color=color, alpha=0.7, label=name)

    # 组合线
    combo_navs = np.array([n for _, n in combo_report.nav_history])
    combo_dates = [t for t, _ in combo_report.nav_history]
    ax.plot(combo_dates, combo_navs / 1_000_000, "k", lw=2.5, label="Combo")
    ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
    ax.legend(ncol=2, fontsize=8)
    ax.set_title("4 Strategies + Combo", fontweight="bold")
    ax.set_ylabel("Net Value"); ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    st.pyplot(fig)
    plt.close(fig)

    # ── 相关性矩阵 ──
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔗 策略日收益相关性")
        if not corr_matrix.empty:
            fig2, ax2 = plt.subplots(figsize=(5, 5))
            im = ax2.imshow(corr_matrix, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
            names = list(corr_matrix.columns)
            ax2.set_xticks(range(len(names))); ax2.set_yticks(range(len(names)))
            ax2.set_xticklabels(names, rotation=45, ha="right", fontsize=9)
            ax2.set_yticklabels(names, fontsize=9)
            for i in range(len(names)):
                for j in range(len(names)):
                    ax2.text(j, i, f"{corr_matrix.iloc[i,j]:.3f}", ha="center", va="center",
                            fontsize=9, color="white" if abs(corr_matrix.iloc[i,j])>0.4 else "black")
            ax2.set_title("Strategy Correlation Matrix", fontweight="bold")
            plt.colorbar(im, shrink=0.8)
            st.pyplot(fig2)
            plt.close(fig2)

    with col2:
        st.subheader("📋 组合资金分配")
        if hasattr(combo_report, "weights") or True:
            st.markdown("""
            **波动率倒数加权 (InvVol):**
            - 高波动策略 → 分配少
            - 低波动策略 → 分配多
            - 每个策略贡献相同波动

            **为什么？**
            - 波动率有持续性(可预测)
            - 收益没有持续性(不可预测)
            - → 比Max Sharpe更稳健
            """)

    # ── 组合绩效 ──
    st.divider()
    st.subheader("🏆 组合绩效")
    cols = st.columns(4)
    cols[0].metric("组合 Sharpe", f"{combo_report.sharpe_ratio:.3f}",
                   delta=f"{combo_report.sharpe_ratio - np.mean([r.sharpe_ratio for r in reports.values()]):.3f} vs avg")
    cols[1].metric("组合 MDD", f"{combo_report.max_drawdown*100:.2f}%")
    cols[2].metric("组合收益", f"{combo_report.total_return*100:.2f}%")
    cols[3].metric("组合波动", f"{combo_report.annual_volatility*100:.1f}%")
