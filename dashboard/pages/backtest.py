"""回测页 — 选策略 → 设参数 → 跑 → 看报告"""
import streamlit as st
import pandas as pd
import numpy as np

from dashboard.components import nav_chart, drawdown_chart, report_table
from data.store import DataStore
from data.sources.ashare import AShareSource
from backtest.engine import BacktestEngine
from backtest.strategy import DualMAStrategy, BuyAndHoldStrategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy


STRATEGIES = {
    "Buy & Hold (基准)": ("base", None),
    "双均线 DualMA": ("dual", None),
    "布林带 Bollinger": ("bollinger", None),
    "海龟 Turtle": ("turtle", None),
    "RSRS 阻力支撑": ("rsrs", None),
}

SYMBOLS = {
    "沪深300 (sh.000300)": "sh.000300",
    "贵州茅台 (sh.600519)": "sh.600519",
    "宁德时代 (sz.300750)": "sz.300750",
    "招商银行 (sh.600036)": "sh.600036",
}


def show():
    st.title("🧪 策略回测")

    # ── 左侧栏：参数配置 ──
    with st.sidebar:
        st.subheader("回测参数")

        strategy_name = st.selectbox("策略", list(STRATEGIES.keys()))

        symbol_label = st.selectbox("品种", list(SYMBOLS.keys()))
        symbol = SYMBOLS[symbol_label]

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("起始日", pd.Timestamp("2024-01-01"))
        with col2:
            end_date = st.date_input("结束日", pd.Timestamp("2024-12-31"))

        st.divider()
        st.subheader("策略参数")

        strategy_key = STRATEGIES[strategy_name][0]

        if strategy_key == "dual":
            short = st.slider("短期均线", 2, 20, 5)
            long = st.slider("长期均线", 5, 60, 20)
        elif strategy_key == "bollinger":
            period = st.slider("均线周期", 5, 50, 20)
            k = st.slider("标准差倍数", 1.0, 3.0, 2.0, 0.1)
        elif strategy_key == "turtle":
            entry = st.slider("入场周期", 5, 60, 20)
            exit_p = st.slider("出场周期", 5, 30, 10)
            atr_p = st.slider("ATR 周期", 7, 30, 20)
        elif strategy_key == "rsrs":
            window = st.slider("回归窗口", 5, 40, 18)
            buy_th = st.slider("买入阈值", 0.1, 1.5, 0.5, 0.1)
            sell_th = st.slider("卖出阈值", -1.5, -0.1, -0.5, 0.1)

        st.divider()
        initial_cash = st.number_input("初始资金", 100_000, 100_000_000, 1_000_000, 100_000)
        slippage = st.slider("滑点", 0.0, 0.01, 0.001, 0.001, format="%.3f")
        commission = st.slider("手续费率", 0.0, 0.005, 0.0003, 0.0001, format="%.4f")

        run_btn = st.button("▶ 运行回测", type="primary", use_container_width=True)

    # ── 主区域：结果 ──
    if not run_btn:
        st.info("👈 在左侧栏配置参数后，点击「运行回测」")
        st.markdown("""
        ### 使用说明
        1. **选策略**：从下拉菜单选择要回测的策略
        2. **选品种**：选择股票或指数
        3. **调参数**：拖动滑块调整策略参数
        4. **跑回测**：点击按钮等待结果
        """)
        return

    with st.spinner(f"正在回测 {strategy_name} on {symbol} ..."):
        # 加载数据
        store = DataStore("data/quant.db")
        df = store.load("ashare", "daily", symbols=[symbol],
                        start=start_date.isoformat(), end=end_date.isoformat())

        if df.empty:
            ashare = AShareSource()
            df = ashare.get_history([symbol], start_date.isoformat(), end_date.isoformat())
            if not df.empty:
                store.save(df, "ashare", "daily")
            else:
                st.error("无法获取数据，请检查网络或 baostock 连接")
                return

        # 构建策略
        if strategy_key == "base":
            strategy = BuyAndHoldStrategy()
        elif strategy_key == "dual":
            strategy = DualMAStrategy(short, long)
        elif strategy_key == "bollinger":
            strategy = BollingerStrategy(period, k)
        elif strategy_key == "turtle":
            strategy = TurtleStrategy(entry, exit_p, atr_p, 2.0)
        elif strategy_key == "rsrs":
            strategy = RSRSStrategy(window, buy_th, sell_th)
        else:
            st.error("未知策略")
            return

        # 运行
        engine = BacktestEngine(df, strategy, initial_cash, slippage, commission)
        report = engine.run()

    # ── 显示结果 ──
    st.success(f"回测完成 — {strategy_name} on {symbol_label}")

    st.subheader("📊 绩效指标")
    report_table(report)

    st.divider()
    st.subheader("📈 净值曲线")
    nav_chart(report.nav_history, f"{strategy_name} — Net Value")

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("📉 回撤曲线")
        drawdown_chart(report.nav_history)

    with col_b:
        st.subheader("📋 关键指标")
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
