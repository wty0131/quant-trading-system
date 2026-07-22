# 📊 量化交易系统 (Quantitative Trading System)

基于 Python 的 A 股量化交易系统，覆盖**数据采集 → 策略研究 → 回测验证 → 风控管理 → 实盘执行**完整链路。

> v2.0 — A 股专用 | 158 只股票池 | 10 种策略 | Streamlit 5 页仪表盘 | 网页内编辑自定义策略

## ✨ 功能模块

### 📥 数据层
- **A 股数据源**：baostock 直连，无需 Token，无需代理
- **统一抽象接口**：`DataSource` 基类 → `get_history()` 一键拉取
- **标准化管道**：列名映射 → 类型转换 → 去重排序 → 时区归一化
- **SQLite 存储**：WAL 模式 + UPSERT 语义，按市场+周期分表

### ⚙️ 回测引擎
- **事件驱动架构**：`MarketEvent → Signal → Order → Fill` 完整链
- **逐笔回放**：杜绝前瞻偏差，模拟真实交易时序
- **仿真撮合**：可配置滑点与佣金
- **绩效报告**：总收益 / 夏普 / Sortino / 最大回撤 / Calmar / 胜率 / 盈亏比

### 📈 策略库（10 个）
| 策略 | 分类 | 说明 |
|------|------|------|
| 买入持有 (基准) | 基准对照 | 验证引擎正确性 |
| 双均线 | 趋势跟踪 | MA 金叉/死叉 |
| 布林带 | 均值回归 | 突破上下轨反向交易 |
| 海龟交易系统 | 趋势跟踪 | 突破入场 + ATR 止损 + 金字塔加仓 |
| RSRS 阻力支撑 | 量价结构 | OLS 回归斜率量化买卖力量 |
| 多因子选股 | 截面 Alpha | 动量/反转/低波因子打分 |
| 配对交易 | 统计套利 | 协整价差 Z-Score 回归 |
| SVM 机器学习 | 机器学习 | 15 天 K 线特征 → SVM 预测涨跌 |
| ARIMA 预测 | 时间序列 | ARIMA 模型预测短期走势 |
| 上证50 轮动 | 指数增强 | 50 只成分股 MA 交叉轮动 |

### 📊 仪表盘（5 页）
| 页面 | 功能 |
|------|------|
| 总览 | 净值曲线、收益卡片、持仓饼图、回撤分析 |
| 策略 | 10 策略全景对比 + 净值 + 回撤 + 相关性矩阵 |
| 回测 | 158 只股票 × 全部策略 → 选参数 → 一键回测 |
| 风控 | 风险仪表、仓位监控、风控规则检查 |
| ✏️ 自定义策略 | **网页内直接写 Python 代码 → 保存即生效** |

### ✏️ 自定义策略（零命令行）
无需手动创建 `.py` 文件。打开仪表盘 → 「自定义策略」页面 → 在代码编辑器中写 `on_bar()` → 点击保存 → 去回测页立刻能用。`__init__` 参数自动变成滑块。

### 🛡️ 风控
- 资金分配：等权 / 波动率倒数 / Max Sharpe
- 头寸管理：固定比例 / Kelly 公式 / 风险平价 / 波动率目标
- 止损系统：固定 / ATR / 移动 / 时间止损
- 策略组合引擎：多策略净值加权合并

### 🚀 执行层
- **OMS 订单状态机**：PENDING → PARTIAL → FILLED → CANCELLED
- **纸交易引擎**：零风险模拟验证
- **A 股实盘接口**：QMT / xtquant（长城证券适配）
- **TWAP 执行算法**：时间加权拆单
- **独立风控守护**：日亏损上限 / 最大回撤 / 仓位限制

### 📓 Jupyter Notebook（6 个）
- `00_data_exploration` — 数据探索入门
- `01_data_pipeline` — 数据管道与三层架构
- `02_backtest_engine` — 事件驱动回测引擎
- `03_strategies` — 策略开发与回测对比
- `04_risk_portfolio` — 风控与多策略组合
- `05_live_execution` — 实盘执行与纸交易

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────┐
│                 Streamlit Dashboard (5页)            │
│   总览 / 策略 / 回测 / 风控 / 自定义策略               │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              策略注册中心 (自动发现新策略)              │
│  双均线 │ 布林带 │ 海龟 │ RSRS │ SVM │ ARIMA │ ...  │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              事件驱动回测引擎                          │
│  MarketEvent → Signal → Order → Fill → Analytics     │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              风控层 + 执行层                           │
│  Allocation │ Sizing │ Stops │ Combiner              │
│  OMS │ TWAP │ Paper Broker │ QMT Broker             │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│              数据层 (baostock 直连 + SQLite)          │
│  158 只 A 股，16 个行业，2020-2026 日线数据            │
└──────────────────────────────────────────────────────┘
```

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 仪表盘 | Streamlit + Matplotlib |
| 回测引擎 | Python 事件驱动 |
| 数据源 | baostock（A 股直连） |
| 存储 | SQLite WAL + Pandas |
| ML/统计 | scikit-learn (SVM)、statsmodels (ARIMA) |
| 实盘接口 | xtquant / QMT（长城证券） |
| 研究环境 | Jupyter Notebook |

## 📁 项目结构

```
quant_system/
├── dashboard/                # Streamlit 仪表盘 (5页)
│   ├── app.py                # 主入口
│   ├── components.py         # 图表组件 (净值/回撤/饼图/指标卡)
│   └── tabs/
│       ├── overview.py       # 总览
│       ├── strategies.py     # 10 策略全景对比
│       ├── backtest.py       # 158 只 A 股回测
│       ├── risk.py           # 风控监控
│       └── custom.py         # ✏️ 网页内写代码
│
├── data/                     # 数据层
│   ├── schema.py             # OHLCV 列定义
│   ├── store.py              # SQLite DataStore
│   └── sources/
│       ├── base.py           # DataSource 抽象基类
│       └── ashare.py         # A 股数据源 (baostock)
│
├── backtest/                 # 事件驱动回测引擎
│   ├── engine.py             # 主循环
│   ├── event.py              # 事件类型
│   ├── strategy.py           # Strategy 基类 + QMT 指标
│   ├── portfolio.py          # 组合追踪
│   ├── execution.py          # 仿真撮合
│   └── analytics.py          # 绩效报告
│
├── strategies/               # 策略库
│   ├── registry.py           # 策略注册中心 (自动发现)
│   ├── _template.py          # 用户策略模版
│   ├── bollinger.py          # 布林带
│   ├── turtle.py             # 海龟交易
│   ├── rsrs.py               # RSRS
│   ├── multifactor.py        # 多因子
│   ├── pairs.py              # 配对交易
│   ├── qmt_svm.py            # SVM (QMT 适配)
│   ├── qmt_arima.py          # ARIMA (QMT 适配)
│   └── qmt_index_ma.py       # 上证50 轮动 (QMT 适配)
│
├── execution/                # 执行层
│   ├── broker.py             # Broker 抽象接口
│   ├── paper_broker.py       # 纸交易
│   ├── paper_engine.py       # 纸交易引擎
│   ├── qmt_broker.py         # A 股实盘 (QMT)
│   ├── oms.py                # 订单管理 (状态机)
│   ├── twap.py               # TWAP 拆单算法
│   └── risk_guard.py         # 独立风控守护
│
├── risk/                     # 风控模块
│   ├── allocator.py          # 资金分配
│   ├── combiner.py           # 策略组合
│   ├── sizing.py             # 头寸管理
│   └── stops.py              # 止损系统
│
├── indicators/               # QMT 流动性因子
├── notebooks/                # Jupyter (6 个)
├── tests/                    # 测试 (6 个)
├── scripts/                  # Notebook 构建脚本
├── requirements.txt
└── README.md
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Windows / macOS / Linux

### 安装

```bash
git clone https://github.com/wty0131/quant-trading-system.git
cd quant-trading-system
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 启动仪表盘

```bash
streamlit run dashboard/app.py
```

浏览器打开 `http://localhost:8501` → 无需任何配置。

### 启动研究环境

```bash
jupyter notebook notebooks/
```

## ✏️ 添加你的策略（三种方式）

### 方式 1：网页编辑器（推荐）
打开仪表盘 → 「自定义策略」→ 写代码 → 保存 → 去回测页下拉菜单选择。

### 方式 2：复制模板
```bash
cp strategies/_template.py strategies/my_strategy.py
# 编辑 my_strategy.py → 重启仪表盘
```

### 方式 3：从零创建
在 `strategies/` 下放一个 `.py` 文件，类继承 `Strategy`，实现 `on_bar()`，设置 `name` / `category` / `description` 三个属性即可。重启仪表盘自动发现。

```python
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent

class MyStrategy(Strategy):
    name = "我的策略"
    category = "用户自定义"
    description = "简单描述"

    def __init__(self, ma_period: int = 20):
        super().__init__()
        self.ma_period = ma_period
        self._in_position = False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        ma = self.sma(bar.symbol, self.ma_period)
        if ma is None:
            return None
        if bar.close > ma and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif bar.close < ma and self._in_position:
            self._in_position = False
            return self._ask(bar)
        return None
```

### on_bar() 可用方法

| 方法 | 说明 |
|------|------|
| `self.sma(symbol, period)` | 简单移动平均 |
| `self.ema(symbol, period)` | 指数移动平均 |
| `self.highest(symbol, period)` | N 日最高价 |
| `self.lowest(symbol, period)` | N 日最低价 |
| `self.atr(symbol, period)` | 平均真实波幅 |
| `self.dastd(symbol, period)` | 半衰期加权波动率 |
| `self.hsigma(sym, idx, period)` | 加权 Beta |
| `self.cmra(symbol)` | 12 月累计收益范围 |
| `self._bid(bar)` | 生成买入信号 |
| `self._ask(bar)` | 生成卖出信号 |

## 📋 回测结果示例

以下为 10 个策略在沪深300 2024 年日线数据上的回测对比（模拟数据，仅展示报告格式）：

| 指标 | 说明 |
|------|------|
| 总收益率 / 年化收益率 | 策略整体表现 |
| 年化波动率 | 净值波动程度 |
| 夏普比率 | >0.5 值得考虑，>1 优秀 |
| 最大回撤 | 绝对值 <15% 可接受 |
| Calmar 比率 | 年化收益 / 最大回撤的绝对值 |
| 胜率 / 盈亏比 | 交易层面表现 |

> ⚠ 回测结果不等于实盘表现。历史收益不保证未来收益。

## ⚠️ 免责声明

- 本系统仅供**学习研究**使用，不构成任何投资建议
- 回测结果不代表实盘表现，历史收益不保证未来收益
- 量化交易存在风险，实盘交易可能导致本金亏损
- 使用本系统进行的任何交易操作，风险由使用者自行承担

## 📄 License

MIT License
