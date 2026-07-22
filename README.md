# 📊 量化交易系统 (Quantitative Trading System)

基于 Python 的 A 股量化交易系统，覆盖**数据采集 → 策略研究 → 回测验证 → 风控管理 → 实盘执行**完整链路。

> v2.0 — A 股专用 | 事件驱动回测引擎 | 10 种内置策略 | Streamlit 可视化仪表盘

## ✨ 功能模块

### 📥 数据层 (Data)
- **A 股数据源**：baostock 直连，无需 Token，无需代理
- **统一抽象接口**：`DataSource` 基类 → `get_history()` 方法
- **标准化处理管道**：列名映射 → 类型转换 → 去重排序 → 时区归一化
- **SQLite 存储**：WAL 模式，UPSERT 语义

### ⚙️ 回测引擎 (Backtest)
- **事件驱动架构**：`MarketEvent → Signal → Order → Fill` 完整事件链
- **逐笔回放**：bar-by-bar 模拟真实交易时序，杜绝前瞻偏差
- **仿真撮合**：可配置滑点与佣金模型
- **绩效报告**：总收益 / 夏普比率 / 最大回撤 / Calmar / Sortino / 胜率 / 盈亏比

### 📈 策略库 (Strategies) — 10 个策略
- **经典策略**：双均线、布林带、海龟交易、RSRS 阻力支撑、多因子选股、配对交易
- **机器学习**：SVM 择时、ARIMA 预测
- **指数增强**：上证50 成分轮动策略

### 📊 仪表盘 (Dashboard)
- **Streamlit Web 界面**：4 页导航（总览 / 策略 / 回测 / 风控）
- **回测页**：47 只 A 股可选 → 9 个策略 → 一键回测 → 全指标可视化
- **策略对比页**：10 个策略全景对比 + 净值曲线 + 回撤 + 相关性矩阵

### 🛡️ 风控 (Risk)
- 资金分配（等权 / 波动率倒数 / Max Sharpe）
- 头寸管理（固定比例 / Kelly 公式 / 风险平价 / 波动率目标）
- 止损系统（固定 / ATR / 移动 / 时间）
- 多策略组合引擎

### 🚀 执行层 (Execution)
- **订单管理系统 (OMS)**：`PENDING → PARTIAL → FILLED → CANCELLED` 状态机
- **纸交易引擎**：模拟撮合，零风险验证策略
- **A 股实盘接口**：QMT / xtquant（长城证券适配）
- **TWAP 执行算法**

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────┐
│                 Streamlit Dashboard                   │
│   总览 / 策略 / 回测 / 风控                            │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│                    Strategy Layer (10策略)             │
│  双均线 │ 布林带 │ 海龟 │ RSRS │ 多因子 │ 配对 │ ...  │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│               Event-Driven Backtest Engine            │
│  MarketEvent → Signal → Order → Fill → Analytics     │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│                     Risk Layer                         │
│  Allocation │ Sizing │ Stops │ Combiner               │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│                  Execution Layer                       │
│  OMS (State Machine) │ TWAP │ Paper Broker │ QMT     │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│                     Data Layer                         │
│              A 股 (baostock 直连)                       │
│          └─────────── SQLite (WAL) ───────────┘       │
└──────────────────────────────────────────────────────┘
```

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| **仪表盘** | Streamlit + Matplotlib |
| **回测引擎** | Python 事件驱动架构 |
| **数据源** | baostock（A 股直连） |
| **数据存储** | SQLite（WAL 模式）+ Pandas |
| **策略建模** | scikit-learn（SVM）、statsmodels（ARIMA） |
| **实盘接口** | xtquant / QMT（长城证券） |
| **研究环境** | Jupyter Notebook |

## 📁 项目结构

```
quant_system/
├── dashboard/                # Streamlit 仪表盘
│   ├── app.py                # 主入口
│   ├── components.py         # 可复用图表组件
│   └── tabs/
│       ├── overview.py       # 总览
│       ├── strategies.py     # 10 策略全景对比
│       ├── backtest.py       # 47 只 A 股回测
│       └── risk.py           # 风控监控
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
│   ├── strategy.py           # Strategy 基类 + 内置指标
│   ├── portfolio.py          # 组合追踪
│   ├── execution.py          # 仿真撮合
│   └── analytics.py          # 绩效报告
│
├── strategies/               # 策略库
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
│   ├── oms.py                # 订单管理
│   ├── twap.py               # TWAP 算法
│   └── risk_guard.py         # 事前风控
│
├── risk/                     # 风控模块
│   ├── allocator.py          # 资金分配
│   ├── combiner.py           # 策略组合
│   ├── sizing.py             # 头寸管理
│   └── stops.py              # 止损系统
│
├── indicators/               # QMT 指标
├── notebooks/                # Jupyter 研究流水线 (6 个)
├── tests/                    # 测试
├── requirements.txt
└── README.md
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- Git

### 2. 安装

```bash
git clone https://github.com/wty0131/quant-trading-system.git
cd quant-trading-system
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 3. 启动仪表盘

```bash
streamlit run dashboard/app.py
```

浏览器访问 `http://localhost:8501` — 无需任何配置，即开即用。

### 4. 启动 Jupyter 研究环境

```bash
jupyter notebook notebooks/
```

## 🔌 添加你的自定义策略

策略自动发现 —— 你只需在 `strategies/` 目录放一个 `.py` 文件，**无需修改任何现有代码**。

### Step 1: 复制模板

```bash
cp strategies/_template.py strategies/my_strategy.py
```

### Step 2: 编写策略

```python
# my_strategy.py
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent

class MyMACDStrategy(Strategy):
    # 元信息 — 仪表盘自动读取
    name = "我的MACD策略"
    category = "用户自定义"
    description = "MACD金叉买入, 死叉卖出"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__()
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self._in_position = False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)

        ema_fast = self.ema(bar.symbol, self.fast)
        ema_slow = self.ema(bar.symbol, self.slow)
        if ema_fast is None or ema_slow is None:
            return None

        if ema_fast > ema_slow and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif ema_fast < ema_slow and self._in_position:
            self._in_position = False
            return self._ask(bar)
        return None
```

### Step 3: 重启仪表盘

```bash
streamlit run dashboard/app.py
```

新策略自动出现在回测页下拉菜单中。`__init__` 的参数（`fast=12`, `slow=26`, `signal=9`）自动变成可拖动滑块。

### 可用的基类方法

| 方法 | 说明 |
|------|------|
| `self.sma(symbol, period)` | 简单移动平均 |
| `self.ema(symbol, period)` | 指数移动平均 |
| `self.highest(symbol, period)` | N日最高价 |
| `self.lowest(symbol, period)` | N日最低价 |
| `self.atr(symbol, period)` | 平均真实波幅 |
| `self.dastd(symbol, period)` | 半衰期加权波动率 |
| `self.hsigma(symbol, idx_sym, period)` | 加权 Beta |
| `self._bid(bar)` | 生成买入信号 |
| `self._ask(bar)` | 生成卖出信号 |

## 📋 内置策略

| 策略 | 类型 | 说明 |
|------|------|------|
| 双均线 | 趋势跟踪 | 短周期均线上穿长周期买入 |
| 布林带 | 均值回归 | 突破上下轨时反向交易 |
| 海龟交易 | 趋势跟踪 | Donchian 通道 + ATR 动态止损 |
| RSRS | 阻力支撑 | 阻力支撑相对强度择时 |
| 多因子选股 | 量化选股 | 动量/反转/波动率多因子打分 |
| 配对交易 | 统计套利 | 协整价差 Z-Score 回归 |
| SVM 择时 | 机器学习 | sklearn SVM 分类器预测涨跌 |
| ARIMA 预测 | 时间序列 | ARIMA 模型预测短期走势 |
| 上证50 轮动 | 指数增强 | 成分股 + MA 择时 |
| Buy & Hold | 基准 | 买入持有基准对照 |

## ⚠️ 免责声明

- 本系统仅供**学习研究**使用，不构成任何投资建议
- 回测结果不代表实盘表现，历史收益不保证未来收益
- 量化交易存在风险，实盘交易可能导致本金亏损
- 使用本系统进行的任何交易操作，风险由使用者自行承担

## 📄 License

MIT License
