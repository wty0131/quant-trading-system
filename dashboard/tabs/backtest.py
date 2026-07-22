"""回测页 — 自动发现全部策略 → 设参数 → 跑 → 看报告"""
import streamlit as st
import pandas as pd
import numpy as np

from dashboard.components import nav_chart, drawdown_chart, report_table
from data.store import DataStore
from data.sources.ashare import AShareSource
from backtest.engine import BacktestEngine
from strategies.registry import get_registry


# ═══════════════════════════════════════════════════════
#  A股股票池 — 100+ 只，按行业分类
#  所有代码经 baostock 验证（sh=沪市, sz=深市）
# ═══════════════════════════════════════════════════════
SYMBOLS = {}

# ── 宽基指数 ──
INDICES = {
    "沪深300": "sh.000300", "上证50": "sh.000016", "中证500": "sh.000905",
    "创业板指": "sz.399006", "科创50": "sh.000688", "深证成指": "sz.399001",
    "上证180": "sh.000010", "中证1000": "sh.000852",
}
SYMBOLS.update({f"📊 {k}": v for k, v in INDICES.items()})

# ── 金融 (银行+保险+证券+多元金融) ──
FINANCE = {
    "招商银行":      "sh.600036", "工商银行":    "sh.601398",
    "建设银行":      "sh.601939", "农业银行":    "sh.601288",
    "中国银行":      "sh.601988", "兴业银行":    "sh.601166",
    "交通银行":      "sh.601328", "邮储银行":    "sh.601658",
    "中国平安":      "sh.601318", "中国人寿":    "sh.601628",
    "中信证券":      "sh.600030", "东方财富":    "sz.300059",
    "华泰证券":      "sh.601688", "同花顺":      "sz.300033",
    "中国太保":      "sh.601601", "中国人保":    "sh.601319",
}
SYMBOLS.update({f"🏦 {k}": v for k, v in FINANCE.items()})

# ── 消费 (白酒+食品+家电+零售+免税) ──
CONSUMER = {
    "贵州茅台":      "sh.600519", "五粮液":      "sz.000858",
    "泸州老窖":      "sz.000568", "山西汾酒":    "sh.600809",
    "洋河股份":      "sz.002304", "古井贡酒":    "sz.000596",
    "伊利股份":      "sh.600887", "海天味业":    "sh.603288",
    "金龙鱼":        "sz.300999", "双汇发展":    "sz.000895",
    "中国中免":      "sh.601888", "安井食品":    "sh.603345",
    "牧原股份":      "sz.002714", "温氏股份":    "sz.300498",
}
SYMBOLS.update({f"🛒 {k}": v for k, v in CONSUMER.items()})

# ── 科技 (半导体+新能源+电子+软件+AI) ──
TECH = {
    "宁德时代":      "sz.300750", "比亚迪":      "sz.002594",
    "隆基绿能":      "sh.601012", "阳光电源":    "sz.300274",
    "中芯国际":      "sh.688981", "海康威视":    "sz.002415",
    "立讯精密":      "sz.002475", "科大讯飞":    "sz.002230",
    "韦尔股份":      "sh.603501", "北方华创":    "sz.002371",
    "中微公司":      "sh.688012", "寒武纪":      "sh.688256",
    "金山办公":      "sh.688111", "用友网络":    "sh.600588",
    "三六零":        "sh.601360", "浪潮信息":    "sz.000977",
}
SYMBOLS.update({f"💻 {k}": v for k, v in TECH.items()})

# ── 医药 (创新药+医疗器械+中药+CXO) ──
PHARMA = {
    "恒瑞医药":      "sh.600276", "药明康德":    "sh.603259",
    "迈瑞医疗":      "sz.300760", "片仔癀":      "sh.600436",
    "长春高新":      "sz.000661", "智飞生物":    "sz.300122",
    "爱尔眼科":      "sz.300015", "通策医疗":    "sh.600763",
    "泰格医药":      "sz.300347", "康龙化成":    "sz.300759",
    "云南白药":      "sz.000538", "同仁堂":      "sh.600085",
    "凯莱英":        "sz.002821", "华熙生物":    "sh.688363",
}
SYMBOLS.update({f"💊 {k}": v for k, v in PHARMA.items()})

# ── 能源/资源 (煤炭+石油+电力+有色) ──
ENERGY = {
    "中国神华":      "sh.601088", "中国石油":    "sh.601857",
    "中国石化":      "sh.600028", "中国海油":    "sh.600938",
    "长江电力":      "sh.600900", "华能水电":    "sh.600025",
    "紫金矿业":      "sh.601899", "洛阳钼业":    "sh.603993",
    "赣锋锂业":      "sz.002460", "天齐锂业":    "sz.002466",
    "中国铝业":      "sh.601600", "山东黄金":    "sh.600547",
    "华能国际":      "sh.600011", "国电电力":    "sh.600795",
}
SYMBOLS.update({f"⚡ {k}": v for k, v in ENERGY.items()})

# ── 制造/工业 (机械+化工+材料+重工) ──
INDUSTRY = {
    "美的集团":      "sz.000333", "格力电器":    "sz.000651",
    "三一重工":      "sh.600031", "万华化学":    "sh.600309",
    "福耀玻璃":      "sh.600660", "海尔智家":    "sh.600690",
    "汇川技术":      "sz.300124", "恒立液压":    "sh.601100",
    "先导智能":      "sz.300450", "浙江鼎力":    "sh.603338",
    "中联重科":      "sz.000157", "潍柴动力":    "sz.000338",
    "宝钢股份":      "sh.600019", "海螺水泥":    "sh.600585",
    "东方雨虹":      "sz.002271", "三棵树":      "sh.603737",
}
SYMBOLS.update({f"🏭 {k}": v for k, v in INDUSTRY.items()})

# ── 地产/基建 ──
PROPERTY = {
    "万科A":         "sz.000002", "保利发展":    "sh.600048",
    "招商蛇口":      "sz.001979", "中国建筑":    "sh.601668",
    "中国中铁":      "sh.601390", "中国交建":    "sh.601800",
    "中国铁建":      "sh.601186", "中国电建":    "sh.601669",
}
SYMBOLS.update({f"🏗️ {k}": v for k, v in PROPERTY.items()})

# ── 通信/互联网 ──
TELECOM = {
    "中国移动":      "sh.600941", "中国联通":    "sh.600050",
    "中兴通讯":      "sz.000063", "中国电信":    "sh.601728",
    "中际旭创":      "sz.300308", "新易盛":      "sz.300502",
    "天孚通信":      "sz.300394", "光迅科技":    "sz.002281",
}
SYMBOLS.update({f"📡 {k}": v for k, v in TELECOM.items()})

# ── 交通运输 ──
TRANSPORT = {
    "京沪高铁":      "sh.601816", "中远海控":    "sh.601919",
    "顺丰控股":      "sz.002352", "大秦铁路":    "sh.601006",
    "上海机场":      "sh.600009", "南方航空":    "sh.600029",
    "中国国航":      "sh.601111", "宁波港":      "sh.601018",
}
SYMBOLS.update({f"🚄 {k}": v for k, v in TRANSPORT.items()})

# ── 汽车及零部件 ──
AUTO = {
    "上汽集团":      "sh.600104", "长城汽车":    "sh.601633",
    "赛力斯":        "sh.601127", "长安汽车":    "sz.000625",
    "广汽集团":      "sh.601238", "吉利汽车":    "sh.600699",
    "拓普集团":      "sh.601689", "德赛西威":    "sz.002920",
    "华域汽车":      "sh.600741", "均胜电子":    "sh.600699",
}
SYMBOLS.update({f"🚗 {k}": v for k, v in AUTO.items()})

# ── 国防军工 ──
DEFENSE = {
    "中航沈飞":      "sh.600760", "航发动力":    "sh.600893",
    "中国船舶":      "sh.600150", "中航光电":    "sz.002179",
    "中国重工":      "sh.601989", "中航西飞":    "sz.000768",
    "振华科技":      "sz.000733", "航天电器":    "sz.002025",
}
SYMBOLS.update({f"🛡️ {k}": v for k, v in DEFENSE.items()})

# ── 传媒/游戏/影视 ──
MEDIA = {
    "分众传媒":      "sz.002027", "芒果超媒":    "sz.300413",
    "三七互娱":      "sz.002555", "世纪华通":    "sz.002602",
    "光线传媒":      "sz.300251", "中国电影":    "sh.600977",
    "万达电影":      "sz.002739",
}
SYMBOLS.update({f"🎬 {k}": v for k, v in MEDIA.items()})

# ── 农林牧渔 ──
AGRICULTURE = {
    "北大荒":        "sh.600598", "隆平高科":    "sz.000998",
    "海大集团":      "sz.002311", "大北农":      "sz.002385",
    "新希望":        "sz.000876", "登海种业":    "sz.002041",
}
SYMBOLS.update({f"🌾 {k}": v for k, v in AGRICULTURE.items()})

# ── 环保/公共事业 ──
UTILITIES = {
    "伟明环保":      "sh.603568", "瀚蓝环境":    "sh.600323",
    "碧水源":        "sz.300070", "三峡能源":    "sh.600905",
    "深圳能源":      "sz.000027",
}
SYMBOLS.update({f"🌿 {k}": v for k, v in UTILITIES.items()})


def _build_strategy_label(meta) -> str:
    """构建策略的下拉菜单显示标签"""
    return f"[{meta.category}] {meta.name}"


def show():
    st.title("策略回测")
    st.caption(f"{len(SYMBOLS)} 只A股 + 自动发现策略 — 16个行业全覆盖")

    # ── 动态获取策略列表 ──
    registry = get_registry()
    all_metas = registry.all()

    # 按分类分组
    by_cat = registry.by_category()
    strategy_choices: dict[str, object] = {}
    for cat, items in by_cat.items():
        for meta in items:
            label = f"[{cat}] {meta.name}"
            strategy_choices[label] = meta

    with st.sidebar:
        st.subheader("回测参数")

        chosen_label = st.selectbox("策略", list(strategy_choices.keys()))
        chosen_meta: object = strategy_choices[chosen_label]

        symbol_label = st.selectbox("品种", list(SYMBOLS.keys()))
        symbol = SYMBOLS[symbol_label]

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("起始日", pd.Timestamp("2020-01-01"),
                                       min_value=pd.Timestamp("2015-01-01"))
        with col2:
            end_date = st.date_input("结束日", pd.Timestamp("2025-12-31"))

        # ── 显示策略描述 ──
        if chosen_meta.description:
            st.caption(f"📖 {chosen_meta.description}")

        # ── 动态生成参数滑块 ──
        st.divider()
        st.subheader("策略参数")

        import inspect
        params_dict = {}
        sig = inspect.signature(chosen_meta.cls.__init__)
        for p_name, p in sig.parameters.items():
            if p_name in ('self',):
                continue
            default = p.default if p.default is not inspect.Parameter.empty else None

            if p_name == 'index_name':
                params_dict[p_name] = st.selectbox(p_name, ["上证50"])
            elif isinstance(default, int):
                lo, hi = _int_range(p_name, default)
                params_dict[p_name] = st.slider(p_name, lo, hi, default)
            elif isinstance(default, float):
                params_dict[p_name] = st.slider(p_name, 0.0, max(10.0, default * 2),
                                                default, 0.1, format="%.1f")
            elif isinstance(default, str) and default == "上证50":
                params_dict[p_name] = st.selectbox(p_name, ["上证50"])
            elif default is None:
                pass
            else:
                params_dict[p_name] = default

        st.divider()
        initial_cash = st.number_input("初始资金", 100_000, 100_000_000, 1_000_000, 100_000)
        slippage = st.slider("滑点", 0.0, 0.01, 0.001, 0.001, format="%.3f")
        commission = st.slider("手续费率", 0.0, 0.005, 0.0003, 0.0001, format="%.4f")

        run_btn = st.button("▶ 运行回测", type="primary", use_container_width=True)

    # ── 主区域 ──
    if not run_btn:
        st.info("👈 在左侧栏配置参数后，点击「运行回测」。新策略只需在 strategies/ 放一个 .py 文件即可自动发现。")
        return

    with st.spinner(f"正在回测 {chosen_meta.name} on {symbol_label} ..."):
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

        # 用注册中心的类 + 动态参数构建策略实例
        strategy = chosen_meta.cls(**params_dict)
        engine = BacktestEngine(df, strategy, initial_cash, slippage, commission)
        report = engine.run()

    st.success(f"回测完成 — {chosen_meta.name} on {symbol_label}")

    st.subheader("绩效指标")
    report_table(report)

    st.divider()
    st.subheader("净值曲线")
    nav_chart(report.nav_history, f"{chosen_meta.name} — Net Value")

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
    """根据参数名推断合理的滑块范围"""
    hints = {'short': (2, 30), 'long': (5, 120),
             'period': (3, 100), 'window': (3, 60),
             'train_days': (30, 500), 'history': (30, 500),
             'entry': (3, 60), 'exit': (3, 60), 'entry_period': (3, 60),
             'exit_period': (3, 30), 'atr_period': (5, 40),
             'feature_days': (3, 40), 'predict_days': (1, 20),
             'refit_freq': (1, 60), 'retrain_freq': (5, 60),
             'max_units': (1, 8), 'top_k': (1, 20),
             'momentum_days': (5, 120), 'reversal_days': (2, 30),
             'vol_days': (5, 60), 'rebalance_days': (5, 60),
             'lookback': (10, 200),
             }
    lo, hi = hints.get(name, (1, max(default * 3, 10)))
    return max(1, lo), max(lo + 1, hi)
