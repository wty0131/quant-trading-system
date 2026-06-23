"""
量化交易系统 — Streamlit 仪表盘

启动: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# 确保可以从项目根 import 模块
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

st.set_page_config(
    page_title="量化交易系统",
    page_icon="📊",
    layout="wide",
)

# ── 侧边栏导航 ──
st.sidebar.title("📊 量化交易系统")
st.sidebar.caption("v1.0 — 6阶段完整系统")

page = st.sidebar.radio(
    "导航",
    ["📊 总览", "📈 策略", "🧪 回测", "🛡️ 风控"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.caption("数据源: baostock + Gate.io + yfinance")
st.sidebar.caption("引擎: 事件驱动回测 + 纸交易")

# ── 路由 ──
if page == "📊 总览":
    from dashboard.pages.overview import show
elif page == "📈 策略":
    from dashboard.pages.strategies import show
elif page == "🧪 回测":
    from dashboard.pages.backtest import show
elif page == "🛡️ 风控":
    from dashboard.pages.risk import show
else:
    from dashboard.pages.overview import show

show()
