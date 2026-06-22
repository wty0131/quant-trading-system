#!/usr/bin/env python3
"""Build 05_live_execution.ipynb"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"display_name": "Python (quant)", "language": "python", "name": "quant"},
    "language_info": {"name": "python", "version": "3.13.2"},
}

def md(s): nb.cells.append(nbf.v4.new_markdown_cell(s))
def code(s): nb.cells.append(nbf.v4.new_code_cell(s))

md("""# 05 执行层 — 从回测到交易

### 回测引擎的隐性假设

```
BacktestEngine:
  SignalEvent → 立即成交 @ bar.close → 更新持仓
  假设: 你的单子一定能成交，价格就是你看到的价格

实盘:
  SignalEvent → 生成订单 → 发送到券商 → 排队等待成交
  → 可能部分成交 → 可能被拒 → 可能价格已经跑了
```

执行层管理**回测不会告诉你的摩擦**。

---
| 章节 | 核心问题 |
|------|---------|
| 1. Broker 统一接口 | 纸交易↓实盘，同一套代码切换 |
| 2. 订单状态机 | 你的单子不会立即成交 |
| 3. 纸交易引擎 | 回测引擎的"实时版" |
| 4. 纸交易 vs 回测 | 同一个策略，两种引擎的差异 |
| 5. 风控守护 | 独立进程监控，策略不能裁判自己 |
| 6. 总结 | 通往实盘的最后一步 |""")

md("""## 1. Broker 统一接口 — 插拔式券商

和 DataSource 同样的 ABC 模式——定义契约，子类实现。

```python
class Broker(ABC):
    def submit_order(...)   # 提交订单
    def get_order_status()  # 查询状态
    def cancel_order()      # 撤单
    def get_positions()     # 持仓
    def get_balance()       # 余额

PaperBroker:   模拟成交，立刻可用
CCXTBroker:    加密实盘 via Gate.io
QMTBroker:     A股实盘 (需券商开通)
```""")

code("""import sys; sys.path.insert(0, "..")
import pandas as pd, numpy as np, matplotlib.pyplot as plt, warnings
warnings.filterwarnings("ignore")
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from execution.paper_broker import PaperBroker
from execution.oms import OrderManager, OrderStatus
from execution.risk_guard import RiskGuard, RiskAction
from execution.paper_engine import PaperTradingEngine
from backtest.strategy import BuyAndHoldStrategy, DualMAStrategy
from backtest.engine import BacktestEngine
from backtest.event import MarketEvent

# 创建纸交易券商
broker = PaperBroker(initial_cash=1_000_000, slippage=0.001, commission_rate=0.0003)
print(f"PaperBroker: cash={broker.cash:,.0f}, slippage={broker.slippage}, fee={broker.commission_rate}")""")

md("""## 2. 订单状态机 — order 的完整生命周期

```
submit_order()
     |
     v
  PENDING ──→ timeout → CANCELLED
     |
     v
  PARTIAL ──→ timeout → CANCELLED (撤剩余)
     |
     v
  FILLED (终态)
```

回测假设立即成交。实盘中订单有独立的生命周期。""")

code("""from execution.oms import OrderManager
import time

# 演示: 提交订单 → 等待成交
oms = OrderManager(broker, timeout_seconds=300)

# 模拟行情
bar = MarketEvent.from_row({
    "date": pd.Timestamp("2024-06-15"), "symbol": "sh.000300",
    "open": 3500, "high": 3550, "low": 3480, "close": 3540, "volume": 1e8,
})

# 提交买入订单
oid = oms.submit("sh.000300", "LONG", 1000)
print(f"Submitted: {oid}")
print(f"Before execution: active={oms.active_count}")

# 行情到来 → 尝试成交
fills = oms.update(bar)
status = broker.get_order_status(oid)
print(f"After market data: status={status['status']} fills={len(fills)}")
print(f"Active orders: {oms.active_count}")

# 查看持仓
print(f"Positions: {broker.get_positions()}")
print(f"Cash left: {broker.cash:,.0f}")""")

md("""## 3. 纸交易引擎 — 回测引擎的"实时版"

```python
PaperTradingEngine vs BacktestEngine:

  相同: strategy.on_bar() → signal → order → fill → mark_to_market
  不同: 数据来源不是 df.iterrows()
        → 是实时拉取的 baostock/ccxt 最新价格
        → 成交走 Broker+OMS 通道（不是立即成交）
```

纸交易引擎用历史数据回放可以对比两种引擎的差异。""")

code("""from backtest.strategy import DualMAStrategy
from data.store import DataStore
from data.sources.ashare import AShareSource

# 准备数据
store = DataStore("../data/quant.db")
df = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01", end="2024-01-15")
if df.empty:
    ashare = AShareSource()
    df = ashare.get_history(["sh.000300"], "2024-01-01", "2024-12-31")
    store.save(df, "ashare", "daily")
df_csi = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01")

print(f"Data: {len(df_csi)} rows, {df_csi['symbol'].nunique()} symbols")

# 回测引擎 (立即成交)
eng_bt = BacktestEngine(df_csi, DualMAStrategy(5, 20), 1_000_000, 0.001, 0.0003)
r_bt = eng_bt.run()

# 纸交易引擎 (走 Broker+OMS)
eng_paper = PaperTradingEngine(DualMAStrategy(5, 20), ["sh.000300"], 1_000_000, 0.001, 0.0003)
r_paper = eng_paper.replay_from_store(df_csi)

print(f"\\nBacktest: return={r_bt.total_return*100:.2f}% sharpe={r_bt.sharpe_ratio:.3f} trades={r_bt.total_trades}")
print(f"Paper:    return={r_paper.total_return*100:.2f}% sharpe={r_paper.sharpe_ratio:.3f} trades={r_paper.total_trades}")
diff = abs(r_bt.total_return - r_paper.total_return)
print(f"Difference: {diff*100:.3f}% (paper走OMS管道vs回测直连的摩擦)")""")

md("""## 4. 纸交易 vs 回测 — 差异怎么来的？""")

code("""# 净值对比
fig, ax = plt.subplots(figsize=(14, 5))
for label, rpt, color in [
    ("Backtest", r_bt, "steelblue"),
    ("Paper", r_paper, "orange"),
]:
    navs = np.array([n for _, n in rpt.nav_history])
    dates = [t for t, _ in rpt.nav_history]
    ax.plot(dates, navs/1_000_000, lw=1.2, label=label, color=color)

ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
ax.set_title("Same Strategy: Backtest vs Paper Engine", fontsize=12, fontweight="bold")
ax.set_ylabel("Net Value"); ax.legend(); ax.grid(True, alpha=0.3)
plt.tight_layout(); plt.show()

print("差异来源:")
print("  1. PaperBroker 成交价 = close*(1+slippage) 回测=close")
print("  2. PaperBroker 整手约束 (100股倍数)")
print("  3. PaperEngine 收敛相同路径需要更多bar构建指标")
print("  4. OMS 管道有 middle-man 开销（尽管纸交易是瞬时的）")""")

md("""## 5. 风控守护 — 策略不能裁判自己

```python
RiskGuard 规则:
  1. 日亏损 > 5% → BLOCK_BUY (只能平不能开)
  2. 最大回撤 > 20% → LIQUIDATE_ALL (全部清仓)
  3. 单品种仓位 > 30% → 拒绝该品种新单
  4. 总仓位 > 80% → 拒绝所有新单
```

为什么必须独立？
- 策略代码如果 crash → 风控仍在运行
- 策略连续报单"疯了" → 风控切断
- 止损写在 on_bar() 里是自己判自己 → 利益冲突""")

code("""# 风控演示
guard = RiskGuard(max_daily_loss=0.05, max_drawdown=0.20,
                  max_position_pct=0.30, max_total_exposure=0.80)
guard.initialize(1_000_000, 1_000_000, pd.Timestamp("2024-06-15").date())

scenarios = [
    ("正常", 1_010_000, {}, "2024-06-15"),
    ("日亏6%", 940_000, {}, "2024-06-15"),
    ("某股仓40%", 1_000_000, {"SH600519": 400_000}, "2024-06-15"),
    ("总仓85%", 1_000_000, {"A": 450_000, "B": 400_000}, "2024-06-15"),
]

for label, nav, pos, dt in scenarios:
    action, reason = guard.check(nav, pos, pd.Timestamp(dt).date())
    print(f"  {label:10s} → {action.value:14s} ({reason})")

# 回撤触发清仓
guard2 = RiskGuard(max_drawdown=0.20)
guard2.initialize(1_000_000, 1_200_000, pd.Timestamp("2024-01-01").date())
guard2.check(1_190_000, {}, pd.Timestamp("2024-01-05").date())
action, reason = guard2.check(940_000, {}, pd.Timestamp("2024-01-10").date())
print(f"  回撤21%    → {action.value:14s} ({reason})")""")

md("""## 6. 总结

### 执行层架构

```
Strategy.on_bar()  →  SignalEvent
                         |
                    RiskGuard.check()  ← 先过风控
                         |
                    OrderManager.submit()  ← 订单状态机
                         |
                    Broker.submit_order()
                    ├── PaperBroker   ← 立刻可用
                    ├── CCXTBroker    ← 加密实盘
                    └── QMTBroker     ← A股实盘 (待开通)
                         |
                    FillEvent → Portfolio.update()
```

### 回测到实盘的鸿沟

| 回测假设 | 实盘真相 |
|---------|---------|
| 看到价格=能成交 | 你的单子排在队列里，可能根本不成交 |
| 立即成交 | PENDING → 等待 → 可能超时撤单 |
| 无滑点 (可配置) | 真实滑点比模型大得多 |
| 无限流动性 | 你的大单会推动价格 |
| 单次 submit | OMS 管理重试、撤单、部分成交 |

### 下一步

纸交易引擎跑 2-4 周 → 对比回测结果偏差 → 调整滑点/手续费模型 → QMT 开通后切实盘。""")

with open("notebooks/05_live_execution.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print("Done: 05_live_execution.ipynb")
