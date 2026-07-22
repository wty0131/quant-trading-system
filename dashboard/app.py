"""
量化交易系统 — Streamlit 仪表盘

启动: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

st.set_page_config(page_title="量化交易系统", page_icon="📊", layout="wide")

# ── 侧边栏 ──
st.sidebar.title("📊 量化交易系统")
st.sidebar.caption("v2.0 — A股专用")

page = st.sidebar.radio(
    "导航",
    ["总览", "策略", "回测", "风控", "自定义策略"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.caption("数据源: baostock 直连")
st.sidebar.caption("引擎: 事件驱动回测 + 纸交易")

if page == "总览":
    from dashboard.tabs.overview import show as _show
elif page == "策略":
    from dashboard.tabs.strategies import show as _show
elif page == "回测":
    from dashboard.tabs.backtest import show as _show
elif page == "风控":
    from dashboard.tabs.risk import show as _show
elif page == "自定义策略":
    from dashboard.tabs.custom import show as _show
else:
    from dashboard.tabs.overview import show as _show

_show()
