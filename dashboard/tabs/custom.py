"""自定义策略页面 — 在网页上直接写策略代码，保存后自动生效"""
import streamlit as st
from pathlib import Path
import importlib
import inspect

STRATEGIES_DIR = Path(__file__).parent.parent.parent / "strategies"

TEMPLATE_CODE = '''"""
在此处写策略原理说明。
"""
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class MyStrategy(Strategy):
    # ── 元信息（显示在仪表盘中）──
    name = "策略名称"
    category = "用户自定义"
    description = "简单描述你的策略逻辑"

    def __init__(self, my_param: int = 20, my_price: float = 2.0):
        """
        所有参数自动变成仪表盘滑块。
        int 参数 → 整数滑块
        float 参数 → 小数滑块
        str 参数 → 文本输入框
        """
        super().__init__()
        self.my_param = my_param
        self.my_price = my_price
        self._in_position = False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        """
        每根K线调用一次。返回 SignalEvent 表示交易信号，None 表示不动。

        bar 属性:
          bar.symbol  股票代码
          bar.close   收盘价
          bar.open    开盘价
          bar.high    最高价
          bar.low     最低价
          bar.volume  成交量

        可用指标:
          self.sma(symbol, 20)   20日均线
          self.ema(symbol, 12)   12日指数均线
          self.atr(symbol, 14)   14日ATR
          self.highest(symbol, 20)  20日最高价
          self.lowest(symbol, 20)   20日最低价
          self._bid(bar)  买入信号  self._ask(bar)  卖出信号
        """
        self._update_price(bar.symbol, bar)

        # ═══════════════════════════════════════
        #   在这里写你的策略逻辑
        # ═══════════════════════════════════════

        ma = self.sma(bar.symbol, self.my_param)
        if ma is None:
            return None

        if bar.close > ma and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif bar.close < ma and self._in_position:
            self._in_position = False
            return self._ask(bar)

        return None
'''


def show():
    st.title("✏️ 自定义策略")
    st.caption("在网页中直接编写策略 → 保存 → 立即生效。无需命令行，无需手动创建文件。")

    # ── 列出已有用户策略 ──
    existing_files = sorted(
        f for f in STRATEGIES_DIR.glob("*.py")
        if not f.name.startswith("_") and not f.name.startswith(".")
        and f.name not in ("__init__.py",)
        and f.name not in (
            "bollinger.py", "turtle.py", "rsrs.py", "multifactor.py",
            "pairs.py", "qmt_svm.py", "qmt_arima.py", "qmt_index_ma.py",
            "registry.py",
        )
    )

    tab1, tab2, tab3 = st.tabs(["📝 新建策略", "📂 我的策略", "📖 帮助"])

    # ═══════════════════ Tab 1: 新建/编辑 ═══════════════════
    with tab1:
        edit_mode = st.radio("模式", ["从模板创建", "编辑已有策略"], horizontal=True)

        if edit_mode == "从模板创建":
            target_file = st.text_input("策略文件名 (不含.py)", "my_strategy",
                                       help="例如: macd_trend, momentum_breakout")
        else:
            if existing_files:
                chosen = st.selectbox("选择要编辑的策略", [f.stem for f in existing_files])
                target_file = chosen
            else:
                st.info("还没有自定义策略，请先创建。")
                target_file = None

        if target_file:
            filepath = STRATEGIES_DIR / f"{target_file}.py"

            # 加载已有代码或模板
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    current_code = f.read()
            else:
                current_code = TEMPLATE_CODE

            code = st.text_area(
                "策略代码 (Python)",
                value=current_code,
                height=500,
                key="custom_strategy_code",
                help="继承 Strategy 基类，实现 on_bar() 方法。保存后自动生效。",
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 保存策略", type="primary", use_container_width=True):
                    # 保存安全校验
                    if "import os" in code and "system" in code.lower() and "os." in code:
                        st.error("⚠ 检测到 os.system 调用，不允许执行系统命令。")
                    else:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(code)
                        st.success(f"✅ 已保存到 strategies/{target_file}.py")
                        st.info("请在左侧回测页查看新策略。如已打开仪表盘，刷新页面即可。")
            with col2:
                if filepath.exists() and st.button("🗑 删除此策略", type="secondary", use_container_width=True):
                    filepath.unlink()
                    st.warning(f"已删除 strategies/{target_file}.py")
                    st.rerun()

            # 预览参数
            st.divider()
            st.subheader("📊 参数预览")
            try:
                # 尝试解析代码中的类
                import tempfile, sys, importlib.util as iu
                spec = iu.spec_from_file_location("_preview", filepath)
                mod = iu.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if hasattr(obj, 'on_bar') and hasattr(obj, 'name') and name != 'Strategy':
                        st.caption(f"类名: {name}")
                        st.caption(f"策略名: {obj.name}")
                        st.caption(f"分类: {getattr(obj, 'category', '未分类')}")
                        sig = inspect.signature(obj.__init__)
                        params = {k: v.default for k, v in sig.parameters.items()
                                  if k != 'self' and v.default is not inspect.Parameter.empty}
                        if params:
                            st.caption(f"参数: {params}")
            except Exception as e:
                st.caption(f"预览: {e}")

    # ═══════════════════ Tab 2: 我的策略列表 ═══════════════════
    with tab2:
        if not existing_files:
            st.info("还没有自定义策略。去「新建策略」页面创建一个。")
        else:
            for f in sorted(existing_files):
                with st.expander(f"📄 {f.stem}"):
                    with open(f, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    st.code(content[:2000] + ("..." if len(content) > 2000 else ""),
                            language="python")
                    st.caption(f"文件大小: {len(content)} 字符")

    # ═══════════════════ Tab 3: 帮助 ═══════════════════════
    with tab3:
        st.markdown("""
        ### 如何写策略

        你的策略就是一个类，继承 `Strategy`，必须实现 `on_bar()` 方法：

        ```python
        class MyStrategy(Strategy):
            name = "我的策略"
            category = "用户自定义"
            description = "简单描述"

            def __init__(self, ...):
                ...

            def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
                # 逻辑 → 返回 signal 或 None
        ```

        ### on_bar() 能用的数据

        | bar 属性 | 含义 |
        |----------|------|
        | `bar.symbol` | 股票代码 |
        | `bar.close` | 收盘价 |
        | `bar.open` | 开盘价 |
        | `bar.high` | 最高价 |
        | `bar.low` | 最低价 |
        | `bar.volume` | 成交量 |

        ### 内置指标

        | 方法 | 说明 |
        |------|------|
        | `self.sma(s, period)` | 简单移动平均 |
        | `self.ema(s, period)` | 指数移动平均 |
        | `self.highest(s, period)` | N日最高价 |
        | `self.lowest(s, period)` | N日最低价 |
        | `self.atr(s, period)` | 平均真实波幅 |
        | `self.dastd(s, period)` | 加权波动率 |
        | `self._bid(bar)` | 开多信号 |
        | `self._ask(bar)` | 平仓信号 |

        ### 常用策略模板

        **趋势跟踪 (金叉买入)**
        ```python
        ma_short = self.sma(bar.symbol, 5)
        ma_long  = self.sma(bar.symbol, 20)
        if ma_short > ma_long and not holding:
            self._in_position = True
            return self._bid(bar)
        ```

        **均值回归 (超跌买入)**
        ```python
        ma = self.sma(bar.symbol, 20)
        if bar.close < ma * 0.95 and not holding:
            self._in_position = True
            return self._bid(bar)
        ```

        **突破追踪 (ATR止损)**
        ```python
        atr = self.atr(bar.symbol, 14)
        highest = self.highest(bar.symbol, 20)
        if bar.close > highest and not holding:
            self._entry_price = bar.close
            self._stop_price = bar.close - 2 * atr
            return self._bid(bar)
        ```
        """)
