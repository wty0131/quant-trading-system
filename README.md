# 📊 量化交易系统 (Quantitative Trading System)

基于 Python 的全栈量化交易系统，覆盖**数据采集 → 策略研究 → 回测验证 → 风控管理 → 实盘执行**完整链路。支持 A 股、加密货币、美股三大市场。

> v1.0 — 6 阶段完整系统 | 事件驱动回测引擎 | 9 种内置策略 | Streamlit 可视化仪表盘

## ✨ 功能模块

### 📥 数据层 (Data)
- **三大市场数据源**：A 股（baostock）、加密货币（ccxt）、美股（yfinance）
- **统一抽象接口**：`DataSource` 基类 → `get_history()` 方法，三市场通用
- **标准化处理管道**：列名映射 → 类型转换 → 去重排序 → 时区归一化
- **SQLite 存储**：WAL 模式，UPSERT 语义，按市场+周期分表

### ⚙️ 回测引擎 (Backtest)
- **事件驱动架构**：`MarketEvent → Signal → Order → Fill` 完整事件链
- **逐笔回放**：bar-by-bar 模拟真实交易时序
- **仿真撮合**：可配置滑点与佣金模型
- **绩效报告**：总收益 / 夏普比率 / 最大回撤 / Calmar 比率 / 年化波动率 / 胜率 / 盈亏比

### 📈 策略库 (Strategies)
- **经典策略**：双均线、布林带、海龟交易、RSRS 阻力支撑、多因子选股、配对交易
- **机器学习策略**：SVM 择时、ARIMA 预测
- **指数增强**：上证50 成分轮动策略
- **可扩展架构**：继承 `Strategy` 基类，实现 `on_bar()` 即可

### 📊 仪表盘 (Dashboard)
- **Streamlit Web 界面**：4 页导航（总览 / 策略 / 回测 / 风控）
- **总览页**：净值曲线、收益指标卡片、持仓饼图、回撤分析
- **回测页**：参数配置 → 一键回测 → 结果可视化
- **数据缓存**：`@st.cache_data` 1小时 TTL，避免重复查询

### 🛡️ 风控 (Risk)
- 资金分配（等权 / 波动率加权）
- 头寸管理（固定比例 / Kelly公式）
- 止损逻辑（固定百分比 / 动态跟踪止损）
- 多策略组合

### 🚀 执行层 (Execution)
- **订单管理系统（OMS）**：完整状态机 `PENDING → PARTIAL_FILLED → FILLED/CANCELLED`
- **纸交易引擎**：模拟撮合，无风险验证策略
- **实盘接口**：CCXT（加密货币）、QMT/xtquant（A股）
- **TWAP 算法**：时间加权平均价格执行
- **事前风控**：下单前自动检查资金/头寸/涨跌停

### 📓 Jupyter Notebook
6 个 Notebook 覆盖完整研究流水线：
- `00_data_exploration.ipynb` — 数据探索
- `01_data_pipeline.ipynb` — 数据管道
- `02_backtest_engine.ipynb` — 回测引擎
- `03_strategies.ipynb` — 策略开发
- `04_risk_portfolio.ipynb` — 风控与组合
- `05_live_execution.ipynb` — 实盘执行

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────┐
│                 Streamlit Dashboard                   │
│   总览 / 策略 / 回测 / 风控                            │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│                    Strategy Layer                      │
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
│  OMS (State Machine) │ TWAP │ Paper Broker │ Live     │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│                     Data Layer                         │
│  A股(baostock) │ 加密(ccxt) │ 美股(yfinance)           │
│  └─────────── SQLite (WAL) ───────────┘               │
└──────────────────────────────────────────────────────┘
```

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| **仪表盘** | Streamlit + Matplotlib |
| **回测引擎** | Python 事件驱动架构（纯手写） |
| **数据源** | baostock（A股）、ccxt（加密货币）、yfinance（美股）|
| **数据存储** | SQLite（WAL 模式） + Pandas |
| **策略建模** | scikit-learn（SVM）、statsmodels（ARIMA）|
| **实盘接口** | xtquant/QMT（A股）、CCXT（加密货币）|
| **研究环境** | Jupyter Notebook |

## 📁 项目结构

```
quant_system/
├── dashboard/                # Streamlit 仪表盘
│   ├── app.py                # 主入口：侧边栏导航 + 页面路由
│   ├── components.py         # 可复用图表组件（净值/回撤/饼图/指标卡）
│   └── pages/
│       ├── overview.py       # 总览：净值曲线 + 收益指标
│       ├── strategies.py     # 策略管理
│       ├── backtest.py       # 回测：参数配置 + 结果展示
│       └── risk.py           # 风控监控
│
├── data/                     # 数据层
│   ├── schema.py             # OHLCV 列定义 + 标准化
│   ├── store.py              # SQLite DataStore（WAL / UPSERT）
│   └── sources/
│       ├── base.py           # DataSource 抽象基类
│       ├── ashare.py         # A 股数据源（baostock）
│       ├── crypto.py         # 加密货币数据源（ccxt）
│       └── usstocks.py       # 美股数据源（yfinance）
│
├── backtest/                 # 事件驱动回测引擎
│   ├── engine.py             # 主循环：逐笔回放
│   ├── event.py              # 事件类型定义
│   ├── strategy.py           # Strategy 基类 + 双均线 + 买入持有
│   ├── portfolio.py          # 组合追踪（现金/持仓/净值）
│   ├── execution.py          # 仿真撮合（滑点/佣金）
│   └── analytics.py          # 绩效报告
│
├── strategies/               # 策略库（9 个策略）
│   ├── bollinger.py          # 布林带策略
│   ├── turtle.py             # 海龟交易系统
│   ├── rsrs.py               # RSRS 阻力支撑相对强度
│   ├── multifactor.py        # 多因子选股
│   ├── pairs.py              # 配对交易
│   ├── qmt_svm.py            # SVM 择时（QMT 集成）
│   ├── qmt_arima.py          # ARIMA 预测（QMT 集成）
│   └── qmt_index_ma.py       # 上证50 成分轮动（QMT 集成）
│
├── execution/                # 执行层
│   ├── broker.py             # Broker 抽象接口
│   ├── paper_broker.py       # 纸交易撮合
│   ├── paper_engine.py       # 纸交易引擎
│   ├── ccxt_broker.py        # 加密货币实盘（CCXT）
│   ├── qmt_broker.py         # A 股实盘（QMT / xtquant）
│   ├── oms.py                # 订单管理系统（状态机）
│   ├── twap.py               # TWAP 执行算法
│   └── risk_guard.py         # 事前风控检查
│
├── risk/                     # 风控模块
│   ├── allocator.py          # 资金分配
│   ├── combiner.py           # 策略组合
│   ├── sizing.py             # 头寸管理
│   └── stops.py              # 止损逻辑
│
├── indicators/               # 自定义指标
├── notebooks/                # Jupyter 研究流水线（6 个）
├── scripts/                  # Notebook 构建脚本
├── tests/                    # 单元测试
├── .env.example              # 环境变量模板
├── requirements.txt          # 依赖列表
└── README.md
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- Git

### 2. 安装

```bash
# 克隆仓库
git clone https://github.com/wty0131/quant-trading-system.git
cd quant_trading_system

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，按需填入你的配置
# 基础使用无需修改任何配置项
```

### 4. 启动仪表盘

```bash
streamlit run dashboard/app.py
```

浏览器访问 `http://localhost:8501`

### 5. 启动 Jupyter 研究环境

```bash
jupyter notebook notebooks/
```

## 📋 内置策略一览

| 策略 | 类型 | 市场 | 说明 |
|------|------|------|------|
| 双均线 | 趋势跟踪 | A股/加密/美股 | 短周期均线上穿长周期买入 |
| 布林带 | 均值回归 | A股/加密/美股 | 突破上下轨时反向交易 |
| 海龟交易 | 趋势跟踪 | A股/加密/美股 | Donchian 通道突破 + ATR 止损 |
| RSRS | 阻力支撑 | A股 | 阻力支撑相对强度指标择时 |
| 多因子选股 | 量化选股 | A股 | 估值/动量/质量多因子打分 |
| 配对交易 | 统计套利 | A股/加密 | 协整检验 + 价差回归 |
| SVM 择时 | 机器学习 | A股 | sklearn SVM 分类器预测涨跌 |
| ARIMA 预测 | 时间序列 | A股 | ARIMA 模型预测短期走势 |
| 指数成分轮动 | 指数增强 | A股 | 上证50 成分股 + 均线择时 |

## ⚠️ 免责声明

- 本系统仅供**学习研究**使用，不构成任何投资建议
- 回测结果不代表实盘表现，历史收益不保证未来收益
- 量化交易存在风险，实盘交易可能导致本金亏损
- 使用本系统进行的任何交易操作，风险由使用者自行承担

## 📄 License

MIT License
