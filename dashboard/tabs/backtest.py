"""回测页 — 自动发现全部策略 → 设参数 → 跑 → 看报告"""
import streamlit as st
import pandas as pd
import numpy as np

from dashboard.components import nav_chart, drawdown_chart, report_table
from data.store import DataStore
from data.sources.ashare import AShareSource
from data.ashare_pool import fetch_all_stocks
from backtest.engine import BacktestEngine
from strategies.registry import get_registry


def show():
    st.title("策略回测")
    st.caption("搜索全市场 5000+ 只A股 → 选策略 → 点运行")

    registry = get_registry()
    by_cat = registry.by_category()
    strategy_choices = {}
    for cat, items in by_cat.items():
        for meta in items:
            strategy_choices[f"[{cat}] {meta.name}"] = meta

    with st.sidebar:
        st.subheader("回测参数")
        chosen_label = st.selectbox("策略", list(strategy_choices.keys()))
        chosen_meta = strategy_choices[chosen_label]

        # ── 股票选择 ──
        search_term = st.text_input("搜索股票名称或代码", "",
                                   placeholder="如: 600519 / 贵州茅台 / 宁德时代")
        if search_term:
            with st.spinner("搜索全市场 5000+ 只A股..."):
                all_stocks = fetch_all_stocks()
                matches = {k: v for k, v in all_stocks.items()
                          if search_term.upper() in k.upper()}
            if matches:
                symbol_label = st.selectbox(f"匹配 {len(matches)} 只", list(matches.keys())[:50])
                symbol = matches[symbol_label]
            else:
                st.warning("未找到匹配股票")
                symbol = None
        else:
            st.caption("输入股票名称或代码搜索 (支持模糊匹配)")
            symbol = None

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("起始日", pd.Timestamp("2020-01-01"))
        with col2:
            end_date = st.date_input("结束日", pd.Timestamp("2025-12-31"))

        if chosen_meta.description:
            st.caption(f"📖 {chosen_meta.description}")

        st.divider()
        st.subheader("策略参数")

        import inspect
        params_dict = {}
        sig = inspect.signature(chosen_meta.cls.__init__)
        for p_name, p in sig.parameters.items():
            if p_name in ("self",):
                continue
            default = p.default if p.default is not inspect.Parameter.empty else None
            if isinstance(default, str) and default == "上证50":
                params_dict[p_name] = st.selectbox(p_name, ["上证50"])
            elif isinstance(default, int):
                lo, hi = _int_range(p_name, default)
                params_dict[p_name] = st.slider(p_name, lo, hi, default)
            elif isinstance(default, float):
                params_dict[p_name] = st.slider(p_name, 0.0, max(10.0, default * 2), default, 0.1, format="%.1f")
            elif default is not None and not isinstance(default, bool):
                params_dict[p_name] = default

        st.divider()
        initial_cash = st.number_input("初始资金", 100_000, 100_000_000, 1_000_000, 100_000)
        slippage = st.slider("滑点", 0.0, 0.01, 0.001, 0.001, format="%.3f")
        commission = st.slider("手续费率", 0.0, 0.005, 0.0003, 0.0001, format="%.4f")
        run_btn = st.button("▶ 运行回测", type="primary", use_container_width=True)

    if not run_btn:
        st.info("👈 在左侧栏配置参数后点击「运行回测」。可选精选池或搜索全市场 5200+ 只任意股票。")
        return

    if symbol is None:
        st.error("请先选择或搜索一只股票")
        return

    with st.spinner(f"正在回测 {chosen_meta.name} on {symbol_label} ..."):
        store = DataStore("data/quant.db")
        df = store.load("ashare", "daily", symbols=[symbol], start=start_date.isoformat(), end=end_date.isoformat())
        if df.empty:
            ashare = AShareSource()
            df = ashare.get_history([symbol], start_date.isoformat(), end_date.isoformat())
            if not df.empty:
                store.save(df, "ashare", "daily")
            else:
                st.error("无法获取数据")
                return

        strategy = chosen_meta.cls(**params_dict)
        engine = BacktestEngine(df, strategy, initial_cash, slippage, commission)
        report = engine.run()

    st.success(f"回测完成 — {chosen_meta.name} on {symbol_label}")
    st.subheader("绩效指标")
    report_table(report)
    st.divider()
    st.subheader("净值曲线")
    nav_chart(report.nav_history, f"{chosen_meta.name}")
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("回撤曲线")
        drawdown_chart(report.nav_history)
    with col_b:
        st.subheader("关键指标")
        st.markdown(f"""
        | 指标 | 值 |
        |------|-----|
        | 总收益率 | {report.total_return*100:.2f}% |
        | 年化收益率 | {report.annual_return*100:.2f}% |
        | 年化波动率 | {report.annual_volatility*100:.2f}% |
        | 夏普比率 | {report.sharpe_ratio:.3f} |
        | 索提诺比率 | {report.sortino_ratio:.3f} |
        | 最大回撤 | {report.max_drawdown*100:.2f}% |
        | 卡尔玛比率 | {report.calmar_ratio:.3f} |
        | 胜率 | {report.win_rate*100:.1f}% |
        | 盈亏比 | {report.profit_factor:.2f} |
        | 总交易 | {report.total_trades} |
        | 持仓占比 | {report.position_ratio*100:.1f}% |
        """)


def _int_range(name, default) -> tuple:
    hints = {
        "short": (2, 30), "long": (5, 120), "period": (3, 100), "window": (3, 60),
        "train_days": (30, 500), "history": (30, 500), "entry": (3, 60),
        "exit": (3, 60), "entry_period": (3, 60), "exit_period": (3, 30),
        "atr_period": (5, 40), "feature_days": (3, 40), "predict_days": (1, 20),
        "refit_freq": (1, 60), "retrain_freq": (5, 60), "max_units": (1, 8),
        "top_k": (1, 20), "momentum_days": (5, 120), "reversal_days": (2, 30),
        "vol_days": (5, 60), "rebalance_days": (5, 60), "lookback": (10, 200),
    }
    lo, hi = hints.get(name, (1, max(default * 3, 10)))
    return max(1, lo), max(lo + 1, hi)
