#!/usr/bin/env python3
"""Build 02_backtest_engine.ipynb"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {
        "display_name": "Python (quant)",
        "language": "python",
        "name": "quant",
    },
    "language_info": {"name": "python", "version": "3.13.2"},
}

def md(s):
    nb.cells.append(nbf.v4.new_markdown_cell(s))

def code(s):
    nb.cells.append(nbf.v4.new_code_cell(s))

# ===== 0: Title =====
md("""# 02 回测引擎 -- 事件驱动架构

### 为什么需要引擎？

Notebook 00 的双均线是"一锤子买卖" -- 对整个 DataFrame 做向量化运算。能看趋势，但有三个问题：

| 问题 | 例子 |
|------|------|
| 前瞻偏差 | rolling(20) 在 t=19 时能看到 t=20 的数据 |
| 无法止损 | "亏10%就卖"需要知道当前持仓状态 |
| 无法加仓 | "回撤15%补仓"依赖历史净值 |

**事件驱动回测**逐条播放历史数据 -- 在每个 t 时刻，你只知道 t 及之前的信息。这和实盘完全一致。

---
| 章节 | 内容 |
|------|------|
| 1. 事件类型 | MarketEvent / SignalEvent / OrderEvent / FillEvent |
| 2. DataHandler | 从 SQLite 逐条回放数据 |
| 3. Strategy 基类 | on_bar() + 内置指标计算 |
| 4. Portfolio + Execution | 持仓管理 + 撮合模拟 |
| 5. 完整引擎 | 组装 + 买入持有验证 |
| 6. 双均线回测 | 与 Notebook 00 结果对比 |
| 7. 绩效分析 | Sharpe/Sortino/MDD/Calmar/盈亏比 |
| 8. 三市场回测 | 同一策略跑 A股+加密+美股 |""")

# ===== 1: Events =====
md("""## 1. 事件类型 -- 信息的载体

```python
MarketEvent   -- 新K线到达    (DataHandler -> Strategy)
SignalEvent   -- 策略信号      (Strategy -> Portfolio)
OrderEvent    -- 待执行订单    (Portfolio -> Execution)
FillEvent     -- 成交回报      (Execution -> Portfolio)

流转:
  MarketEvent -> Strategy.on_bar() -> SignalEvent
  SignalEvent -> Portfolio.generate_order() -> OrderEvent
  OrderEvent  -> Execution.execute() -> FillEvent
  FillEvent   -> Portfolio.update()
```""")

code("""import sys; sys.path.insert(0, "..")
from backtest.event import MarketEvent, SignalEvent, OrderEvent, FillEvent, Direction
import pandas as pd

# 从一行数据创建 MarketEvent
bar = MarketEvent.from_row({
    "date": pd.Timestamp("2024-06-15"), "symbol": "sh.000300",
    "open": 3500., "high": 3550., "low": 3480., "close": 3540., "volume": 1e8,
})
print(f"MarketEvent: symbol={bar.symbol} close={bar.close}")

# Signal: 开多
sig = SignalEvent(timestamp=bar.timestamp, symbol=bar.symbol, direction=Direction.LONG)
print(f"SignalEvent: {sig.direction}")

# Order -> Fill
from backtest.event import OrderEvent, OrderType
order = OrderEvent(timestamp=bar.timestamp, symbol=bar.symbol, direction=Direction.LONG, order_type=OrderType.MKT, quantity=100)
fill = FillEvent(timestamp=bar.timestamp, symbol=bar.symbol, direction=Direction.LONG, quantity=100, price=3540.0, commission=10.62)
print(f"FillEvent: {fill.quantity}@{fill.price} fee={fill.commission}")""")

# ===== 2: DataHandler =====
md("""## 2. DataHandler -- 数据回放

从 SQLite 加载数据，按时间顺序逐条推送。模拟实盘行情到达的感觉。""")

code("""from data.store import DataStore
from data.sources.ashare import AShareSource

# 先确保有数据
store = DataStore("../data/quant.db")

# 检查是否已有数据，没有就拉取
import os
df_test = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01", end="2024-01-31")
if df_test.empty:
    os.environ.pop("PROXY_SOCKS5", None)
    ashare = AShareSource()
    df = ashare.get_history(["sh.000300", "sh.600519"], "2024-01-01", "2024-06-30")
    store.save(df, "ashare", "daily")
    print(f"已拉取并存储 {len(df)} 行")
else:
    print(f"SQLite 已有数据: {len(df_test)} 行 (无需联网)")

# BacktestEngine 内部自动分组回放，你不需要手动迭代 DataHandler
print("数据就绪 -- 引擎将逐条回放")""")

# ===== 3: Strategy =====
md("""## 3. Strategy 基类 -- 策略只需写 on_bar()

```python
class Strategy(ABC):
    @abstractmethod
    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        ...
```

内置指标（基类提供，策略直接调用）：
- sma(symbol, period) -- 简单移动平均
- ema(symbol, period) -- 指数移动平均
- highest/lowest -- N日极值
- atr(symbol, period) -- 平均真实波幅

**关键**：指标基于 deque 滚动窗口计算 -- 永远看不到未来数据。""")

code("""from backtest.strategy import BuyAndHoldStrategy, DualMAStrategy

# 买入持有 -- 第一天买，最后一天卖（验证引擎正确性的基准）
bh = BuyAndHoldStrategy()

# 双均线 -- 金叉买死叉卖
dual = DualMAStrategy(short=5, long=20)
print(f"Buy&Hold: _bought={bh._bought}")
print(f"DualMA: short={dual.short} long={dual.long}")""")

# ===== 4: Portfolio + Execution =====
md("""## 4. Portfolio + Execution -- 钱和交易

**Portfolio**：资金管理、持仓跟踪、净值记录
**ExecutionHandler**：滑点(默认0.1%) + 手续费(默认万三)""")

code("""from backtest.portfolio import Portfolio
from backtest.execution import ExecutionHandler

pf = Portfolio(initial_cash=1_000_000, position_percent=1.0)
ex = ExecutionHandler(slippage=0.001, commission_rate=0.0003)

# 演示：一笔买入交易
import pandas as pd
sig = SignalEvent(timestamp=pd.Timestamp("2024-06-01"), symbol="sh.000300", direction=Direction.LONG)

order = pf.generate_order(sig, current_price=3500)
print(f"Signal -> Order: qty={order.quantity} shares (约 {order.quantity*3500:,.0f} 元)")

bar_dict = {"close": 3500.0}
fill = ex.execute(order, bar_dict)
print(f"Order -> Fill: {fill.quantity}@{fill.price:.2f} fee={fill.commission:.2f}")

pf.update(fill)
pf.mark_to_market(fill.timestamp, {"sh.000300": 3500})
print(f"After buy: cash={pf.cash:,.0f} pos={pf.positions} nav={pf.current_nav():,.0f}")""")

# ===== 5: Full Engine =====
md("""## 5. 完整引擎 -- 买入持有验证

**核心验证**：回测引擎的买入持有结果，应该与手动计算几乎一致。""")

code("""from backtest.engine import BacktestEngine

# 从 SQLite 加载真实数据
df_bt = store.load("ashare", "daily", symbols=["sh.000300"], start="2020-01-01", end="2025-06-20")

# 零摩擦（方便与手动计算对比）
engine_zero = BacktestEngine(
    df=df_bt,
    strategy=BuyAndHoldStrategy(),
    initial_cash=1_000_000,
    slippage=0.0,
    commission_rate=0.0,
)
report_zero = engine_zero.run()

# 手动计算
first = df_bt[df_bt.symbol=="sh.000300"]["close"].iloc[0]
last = df_bt[df_bt.symbol=="sh.000300"]["close"].iloc[-1]
manual = (last / first) - 1

print(f"手动计算:  {manual*100:.2f}%")
print(f"回测引擎:  {report_zero.total_return*100:.2f}%")
print(f"差异:      {abs(report_zero.total_return-manual)*100:.4f}% (应 < 0.1%)")

# 带摩擦的（模拟真实交易成本）
engine_real = BacktestEngine(
    df=df_bt,
    strategy=BuyAndHoldStrategy(),
    initial_cash=1_000_000,
    slippage=0.001,
    commission_rate=0.0003,
)
report_real = engine_real.run()
print(f"\\n带摩擦: {report_real.total_return*100:.2f}% (低于裸收益 {abs(report_real.total_return-manual)*100:.2f}%)")""")

# ===== 6: Dual MA =====
md("""## 6. 双均线回测 -- 与 Notebook 00 对比""")

code("""# 双均线策略：5日 vs 20日
engine_ma = BacktestEngine(
    df=df_bt,
    strategy=DualMAStrategy(short=5, long=20),
    initial_cash=1_000_000,
    slippage=0.001,
    commission_rate=0.0003,
)
report_ma = engine_ma.run()
print(report_ma)

# 对比买入持有
print(f"\\n买入持有 vs 双均线:")
print(f"  买入持有收益: {report_real.total_return*100:.2f}%")
print(f"  双均线收益:   {report_ma.total_return*100:.2f}%")
print(f"  买入持有MDD:  {report_real.max_drawdown*100:.2f}%")
print(f"  双均线MDD:    {report_ma.max_drawdown*100:.2f}%")

if report_ma.total_trades > 0:
    print(f"\\n策略统计:")
    print(f"  交易次数: {report_ma.total_trades}")
    print(f"  胜率:     {report_ma.win_rate*100:.1f}%")
    print(f"  盈亏比:   {report_ma.profit_factor:.2f}")
    print(f"  持仓占比: {report_ma.position_ratio*100:.1f}%")""")

# ===== 7: Analytics =====
md("""## 7. 绩效分析 -- 全套指标""")

code("""import matplotlib.pyplot as plt
import numpy as np
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 净值曲线 + 回撤
navs = np.array([n for _, n in report_ma.nav_history])
dates = [t for t, _ in report_ma.nav_history]
running_max = np.maximum.accumulate(navs)
drawdowns = (navs - running_max) / running_max

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})

ax1.plot(dates, navs / 1_000_000, "steelblue", lw=1, label="Dual MA (5/20)")
ax1.plot(dates, [nav / 1_000_000 for _, nav in report_real.nav_history], "gray", alpha=0.5, lw=1, label="Buy & Hold")
ax1.axhline(y=1, color="gray", ls="--", alpha=0.3)
ax1.set_title("Dual MA Strategy vs Buy & Hold (CSI 300, 2020-2025)", fontsize=12, fontweight="bold")
ax1.set_ylabel("Net Value")
ax1.legend()
ax1.grid(True, alpha=0.3)

ax2.fill_between(dates, 0, drawdowns*100, color="#ff4444", alpha=0.3)
ax2.plot(dates, drawdowns*100, "#cc0000", lw=0.8)
ax2.set_ylabel("Drawdown %")
ax2.set_xlabel("Date")
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()

print(f"Dual MA (5/20):")
print(f"  Return: {report_ma.total_return*100:.2f}%")
print(f"  Sharpe: {report_ma.sharpe_ratio:.3f}")
print(f"  MDD:    {report_ma.max_drawdown*100:.2f}%")
print(f"  Calmar: {report_ma.calmar_ratio:.3f}")""")

# ===== 8: Multi-market =====
md("""## 8. 三市场回测 -- 同一策略，不同市场""")

code("""import os

# 加载或拉取三市场数据
markets = {}
for mkt, syms in [("ashare", ["sh.000300"]), ("crypto", ["BTC/USDT"]), ("usstock", ["AAPL"])]:
    df = store.load(mkt, "daily", symbols=syms, start="2024-01-01", end="2024-12-31")
    if df.empty:
        if mkt == "ashare":
            from data.sources.ashare import AShareSource
            df = AShareSource().get_history(syms, "2024-01-01", "2024-12-31")
        elif mkt == "crypto":
            os.environ["PROXY_SOCKS5"] = "socks5://127.0.0.1:PORT"
            from data.sources.crypto import CryptoSource
            df = CryptoSource().get_history(syms, "2024-01-01", "2024-12-31")
        elif mkt == "usstock":
            from data.sources.usstocks import USStockSource
            df = USStockSource().get_history(syms, "2024-01-01", "2024-12-31")
        store.save(df, mkt, "daily")
    markets[mkt] = df

# 三个市场同时回测
for mkt, df in markets.items():
    if df.empty:
        print(f"{mkt}: 无数据，跳过")
        continue
    engine = BacktestEngine(df, DualMAStrategy(5, 20), 1_000_000, 0.001, 0.0003)
    r = engine.run()
    print(f"{mkt:8s}: return={r.total_return*100:6.2f}%  sharpe={r.sharpe_ratio:6.3f}  MDD={r.max_drawdown*100:6.2f}%  trades={r.total_trades}")""")

# ===== 9: Summary =====
md("""## 9. 总结

### 事件驱动 vs 向量化

| | 向量化 (N00) | 事件驱动 (N02) |
|------|-------------|-------------|
| 速度 | 快 (毫秒) | 慢 (秒) |
| 前瞻偏差 | 需手动避免 | 架构保证 |
| 止损/限价 | 无法实现 | OOTB |
| 实盘迁移 | 不可能 | 换 Execution 即可 |
| 适用场景 | 快速筛选策略 | 精确评估策略 |

### 引擎结构

```
DataFrame (SQLite) --> BacktestEngine.run()
                          |
               for each bar:
                 strategy.on_bar(bar) -> Signal?
                 portfolio.generate_order() -> Order
                 execution.execute() -> Fill
                 portfolio.update(fill)
                 portfolio.mark_to_market()
                          |
                    BacktestReport
```

### 下一步：策略库

回测引擎就绪。接下来实现 6 个经典策略，在三个市场同时回测对比。""")

# Write
with open("notebooks/02_backtest_engine.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print("Done: 02_backtest_engine.ipynb")
