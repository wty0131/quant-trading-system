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
from strategies.qmt_svm import QMTSVMStrategy
from strategies.qmt_arima import QMTARIMAStrategy
from strategies.qmt_index_ma import QMTIndexMAStrategy


STRATEGIES = {
    "Buy & Hold (基准)": ("base", None),
    "双均线 DualMA": ("dual", None),
    "布林带 Bollinger": ("bollinger", None),
    "海龟 Turtle": ("turtle", None),
    "RSRS 阻力支撑": ("rsrs", None),
    "---": ("sep", None),
    "QMT SVM 机器学习": ("qmt_svm", None),
    "QMT ARIMA 预测": ("qmt_arima", None),
    "QMT 上证50 批量MA": ("qmt_index_ma", None),
}

# ═══════════════════════════════════════════
#  扩展A股股票池 — 50+ 只
# ═══════════════════════════════════════════
SYMBOLS = {}

# 宽基指数
INDICES = {
    "沪深300":        "sh.000300",
    "上证50":         "sh.000016",
    "中证500":        "sh.000905",
    "创业板指":        "sz.399006",
    "科创50":         "sh.000688",
}
SYMBOLS.update({f"📊 {k}": v for k, v in INDICES.items()})

# 行业龙头 — 金融
FINANCE = {
    "招商银行":        "sh.600036",
    "中国平安":        "sh.601318",
    "工商银行":        "sh.601398",
    "建设银行":        "sh.601939",
    "中信证券":        "sh.600030",
}
SYMBOLS.update({f"🏦 {k}": v for k, v in FINANCE.items()})

# 消费
CONSUMER = {
    "贵州茅台":        "sh.600519",
    "五粮液":          "sz.000858",
    "伊利股份":        "sh.600887",
    "海天味业":        "sh.603288",
    "中国中免":        "sh.601888",
}
SYMBOLS.update({f"🛒 {k}": v for k, v in CONSUMER.items()})

# 科技
TECH = {
    "宁德时代":        "sz.300750",
    "比亚迪":          "sz.002594",
    "隆基绿能":        "sh.601012",
    "海康威视":        "sz.002415",
    "中芯国际":        "sh.688981",
    "立讯精密":        "sz.002475",
    "科大讯飞":        "sz.002230",
}
SYMBOLS.update({f"💻 {k}": v for k, v in TECH.items()})

# 医药
PHARMA = {
    "恒瑞医药":        "sh.600276",
    "药明康德":        "sh.603259",
    "迈瑞医疗":        "sz.300760",
    "片仔癀":          "sh.600436",
}
SYMBOLS.update({f"💊 {k}": v for k, v in PHARMA.items()})

# 能源/资源
ENERGY = {
    "中国神华":        "sh.601088",
    "中国石油":        "sh.601857",
    "紫金矿业":        "sh.601899",
    "长江电力":        "sh.600900",
}
SYMBOLS.update({f"⚡ {k}": v for k, v in ENERGY.items()})

# 制造/工业
INDUSTRY = {
    "美的集团":        "sz.000333",
    "格力电器":        "sz.000651",
    "三一重工":        "sh.600031",
    "万华化学":        "sh.600309",
    "福耀玻璃":        "sh.600660",
}
SYMBOLS.update({f"🏭 {k}": v for k, v in INDUSTRY.items()})

# 地产/基建
PROPERTY = {
    "万科A":           "sz.000002",
    "保利发展":        "sh.600048",
    "中国建筑":        "sh.601668",
}
SYMBOLS.update({f"🏗️ {k}": v for k, v in PROPERTY.items()})

# 通信/互联网
TELECOM = {
    "中国移动":        "sh.600941",
    "中国联通":        "sh.600050",
    "中兴通讯":        "sz.000063",
}
SYMBOLS.update({f"📡 {k}": v for k, v in TELECOM.items()})

# 交通运输
TRANSPORT = {
    "京沪高铁":        "sh.601816",
    "中远海控":        "sh.601919",
    "顺丰控股":        "sz.002352",
}
SYMBOLS.update({f"🚄 {k}": v for k, v in TRANSPORT.items()})

# 汽车
AUTO = {
    "上汽集团":        "sh.600104",
    "长城汽车":        "sh.601633",
    "赛力斯":          "sh.601127",
}
SYMBOLS.update({f"🚗 {k}": v for k, v in AUTO.items()})


def show():
    st.title("策略回测")
    st.caption("50+ 只A股 + 9 个策略 — 纯A股，无需代理")

    with st.sidebar:
        st.subheader("回测参数")

        strategy_name = st.selectbox("策略", list(STRATEGIES.keys()))

        symbol_label = st.selectbox("品种", list(SYMBOLS.keys()))
        symbol = SYMBOLS[symbol_label]

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("起始日", pd.Timestamp("2020-01-01"),
                                       min_value=pd.Timestamp("2015-01-01"))
        with col2:
            end_date = st.date_input("结束日", pd.Timestamp("2025-12-31"))

        st.divider()
        st.subheader("策略参数")

        strategy_key = STRATEGIES[strategy_name][0]
        if strategy_key == "sep":
            st.info("请选择上方具体策略类型")
            return

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
        elif strategy_key == "qmt_svm":
            train_days = st.slider("训练天数", 60, 300, 120)
            feature_days = st.slider("特征窗口", 5, 30, 15)
            predict_days = st.slider("预测天数", 1, 10, 5)
            retrain = st.slider("重训练间隔", 5, 60, 20)
        elif strategy_key == "qmt_arima":
            history = st.slider("历史窗口", 60, 300, 120)
            refit = st.slider("重训练间隔", 1, 20, 5)
        elif strategy_key == "qmt_index_ma":
            idx_name = st.selectbox("指数", ["上证50"])
            short = st.slider("短期均线", 2, 20, 5)
            long = st.slider("长期均线", 5, 60, 20)

        st.divider()
        initial_cash = st.number_input("初始资金", 100_000, 100_000_000, 1_000_000, 100_000)
        slippage = st.slider("滑点", 0.0, 0.01, 0.001, 0.001, format="%.3f")
        commission = st.slider("手续费率", 0.0, 0.005, 0.0003, 0.0001, format="%.4f")

        run_btn = st.button("▶ 运行回测", type="primary", use_container_width=True)

    # ── 主区域 ──
    if not run_btn:
        st.info("👈 在左侧栏配置参数后，点击「运行回测」。50+ 只A股可选，无需代理。")
        return

    with st.spinner(f"正在回测 {strategy_name} on {symbol_label} ..."):
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
        elif strategy_key == "qmt_svm":
            strategy = QMTSVMStrategy(train_days, feature_days, predict_days, retrain_freq=retrain)
        elif strategy_key == "qmt_arima":
            strategy = QMTARIMAStrategy(history, refit_freq=refit)
        elif strategy_key == "qmt_index_ma":
            strategy = QMTIndexMAStrategy(idx_name, short, long)
        else:
            st.error("未知策略")
            return

        engine = BacktestEngine(df, strategy, initial_cash, slippage, commission)
        report = engine.run()

    st.success(f"回测完成 — {strategy_name} on {symbol_label}")

    st.subheader("绩效指标")
    report_table(report)

    st.divider()
    st.subheader("净值曲线")
    nav_chart(report.nav_history, f"{strategy_name} — Net Value")

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
