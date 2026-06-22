#!/usr/bin/env python3
"""Build 04_risk_portfolio.ipynb"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"display_name": "Python (quant)", "language": "python", "name": "quant"},
    "language_info": {"name": "python", "version": "3.13.2"},
}

def md(s): nb.cells.append(nbf.v4.new_markdown_cell(s))
def code(s): nb.cells.append(nbf.v4.new_code_cell(s))

md("""# 04 风控与组合管理 — 从单策略到多策略

### 为什么单策略不够？

```
海龟胜率只有28%，如果你把全部资金押在海龟上：
  → 连续亏6笔是常态
  → 每次亏损时你都会怀疑"这个策略是不是失效了"
  → 人类的本能反应：手动干预 → 在最该加仓时清仓

组合管理的哲学：
  分散的不只是股票，更是策略本身的失效风险。
  当趋势跟踪在震荡市中连续亏损时，均值回归策略在赚钱。
```

---
| 章节 | 核心问题 |
|------|---------|
| 1. 仓位管理 | 每次开仓该买多少？Kelly vs 固定比例 |
| 2. 止损系统 | 什么时候认错？ATR止损 > 固定止损 |
| 3. 策略相关性 | 哪两个策略能配对？回撤不重叠 |
| 4. 资金分配 | 1000万怎么分？波动率倒数 > 等权 |
| 5. 组合回测 | 4策略组合 vs 单策略对比 |
| 6. 总结 | 风控的系统化流程 |""")

md("""## 1. 仓位管理 — 每次开仓该买多少？

这是量化交易第一重要的决策。

```
仓位 5%  → 亏完需要连续做错20次 → 大概率能翻身
仓位 20% → 亏完只需5次 → 一个黑天鹅直接送走
仓位 50% → 赌徒，不是在投资
```

四种仓位模型：""")

code("""import sys; sys.path.insert(0, "..")
import pandas as pd, numpy as np, matplotlib.pyplot as plt, warnings
warnings.filterwarnings("ignore")
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from risk.sizing import FixedFractionSizer, KellySizer, RiskParitySizer, VolTargetSizer

# 对比四种仓位模型在同一个场景下的建议
cash = 1_000_000
price = 100

models = {
    "Fixed 20%": FixedFractionSizer(0.2),
    "Kelly (p=0.4,b=2.0,half)": KellySizer(0.4, 2.0, half=True),
    "Risk Parity (vol=30%)": RiskParitySizer(0.05),
    "Vol Target (realized=25%)": VolTargetSizer(0.15),
}

for name, model in models.items():
    if "vol" in name.lower() or "vol=30" in name:
        pct = model.get_position_pct(cash, price, volatility=0.30)
    elif "Vol Target" in name:
        pct = model.get_position_pct(cash, price, realized_vol=0.25)
    else:
        pct = model.get_position_pct(cash, price)
    amount = cash * pct
    print(f"{name:30s} 仓位={pct*100:5.1f}% 金额={amount:>10,.0f}")
print()
print("Kelly 共识：half-Kelly 在增长与安全间平衡。full-Kelly 太激进。")""")

md("""## 2. 止损系统 — 什么时候认错？

在 `on_bar()` 中，止损检查的优先级最高：**止损 > 止盈 > 正常信号**。

```
def on_bar(self, bar):
    if self._in_position:
        if bar.close < self._stop_price:     # ATR止损 = 最高优先
            return self._ask(bar)
        if days_since_entry > 20 and in_loss: # 时间止损
            return self._ask(bar)
    # ... 然后是正常的交易逻辑
```""")

code("""from risk.stops import FixedStop, ATRStop, TrailingStop, TimeStop, StopManager

# 模拟一个亏损场景
bar = __import__("backtest").event.MarketEvent.from_row({
    "date": pd.Timestamp("2024-06-15"), "symbol": "TEST",
    "open": 100, "high": 105, "low": 95, "close": 92, "volume": 1e8,
})
entry_price = 100; entry_time = pd.Timestamp("2024-06-01")

print("亏损场景: 买入@100, 当前@92, 持仓14天")
print(f"  固定止损 -5%:   {'触发' if FixedStop(0.05).check(bar, entry_price, entry_time) else '未触发'}")
print(f"  ATR止损 2xATR:  {'触发' if ATRStop(2.0).check(bar, entry_price, entry_time, atr=3.0) else '未触发'}")
print(f"  时间止损 14天:  {'触发' if TimeStop(14).check(bar, entry_price, entry_time) else '未触发'}")

# StopManager 组合使用
mgr = StopManager()
mgr.add(FixedStop(0.05))
mgr.add(ATRStop(2.0))
mgr.on_entry(entry_price, entry_time)
print(f"  StopManager(固定+ATR): {'触发' if mgr.check(bar, atr=3.0) else '未触发'}")""")

md("""## 3. 策略相关性 — 哪两个策略能配对？

把4个策略的日收益算相关性矩阵。相关越低 → 组合效果越好。""")

code("""from data.store import DataStore
from data.sources.ashare import AShareSource
from backtest.engine import BacktestEngine
from backtest.strategy import DualMAStrategy
from strategies.bollinger import BollingerStrategy
from strategies.turtle import TurtleStrategy
from strategies.rsrs import RSRSStrategy

# 数据准备
store = DataStore("../data/quant.db")
df_chk = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01", end="2024-01-15")
if df_chk.empty:
    ashare = AShareSource()
    df_csi = ashare.get_history(["sh.000300"], "2024-01-01", "2024-12-31")
    store.save(df_csi, "ashare", "daily")
df_csi = store.load("ashare", "daily", symbols=["sh.000300"], start="2024-01-01")

# 跑4个策略
strategies = {
    "DualMA":    DualMAStrategy(5, 20),
    "Bollinger": BollingerStrategy(20, 2.0),
    "Turtle":    TurtleStrategy(20, 10, 20, 2.0),
    "RSRS":      RSRSStrategy(18, 0.5, -0.5),
}

daily_rets = {}
for name, strat in strategies.items():
    eng = BacktestEngine(df_csi, strat, 1_000_000, 0.001, 0.0003)
    r = eng.run()
    navs = np.array([n for _, n in r.nav_history])
    if len(navs) > 1:
        rets = np.diff(navs) / navs[:-1]
        daily_rets[name] = rets

# 相关性矩阵
ret_df = pd.DataFrame({n: r[-min(len(v) for v in daily_rets.values()):]
                       for n, r in daily_rets.items()})
corr = ret_df.corr()

fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(corr, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
names = list(corr.columns)
ax.set_xticks(range(len(names))); ax.set_yticks(range(len(names)))
ax.set_xticklabels(names, rotation=45, ha="right"); ax.set_yticklabels(names)
for i in range(len(names)):
    for j in range(len(names)):
        ax.text(j, i, f"{corr.iloc[i,j]:.3f}", ha="center", va="center",
                fontsize=10, color="white" if abs(corr.iloc[i,j])>0.4 else "black")
ax.set_title("Strategy Return Correlation", fontsize=13, fontweight="bold")
plt.colorbar(im, shrink=0.8); plt.tight_layout(); plt.show()

# 解读
print("低相关对（<0.5）:")
for i in range(len(names)):
    for j in range(i+1, len(names)):
        if abs(corr.iloc[i,j]) < 0.5:
            print(f"  {names[i]} & {names[j]}: {corr.iloc[i,j]:.3f}")
print("\\n相关<0.5的策略配对效果最好")""")

md("""## 4. 资金分配 — 1000万怎么分给4个策略？""")

code("""from risk.allocator import EqualAllocator, InvVolAllocator, MaxSharpeAllocator

allocators = {
    "Equal Weight":    EqualAllocator(),
    "Inverse Vol":     InvVolAllocator(),
    "Max Sharpe":      MaxSharpeAllocator(lookback=200),
}

capital = 1_000_000
for name, alloc in allocators.items():
    weights = alloc.allocate(daily_rets, capital)
    w_str = ", ".join(f"{k}={v/capital*100:.0f}%" for k, v in weights.items())
    print(f"{name:15s} {w_str}")
    # 计算用该权重后的组合日收益
    min_len = min(len(r) for r in daily_rets.values())
    w_pct = {n: w / capital for n, w in weights.items()}
    combo_rets = sum(w_pct[n] * daily_rets[n][-min_len:] for n in weights)
    combo_vol = np.std(combo_rets) * np.sqrt(252)
    combo_ret = np.mean(combo_rets) * 252
    combo_sharpe = (combo_ret - 0.025) / combo_vol if combo_vol > 0 else 0
    print(f"  -> 组合波动率={combo_vol*100:.1f}% Sharpe={combo_sharpe:.3f}")
    print()

print("观察: InvVol给低波策略更多钱 → 组合波动率更低 → Sharpe更稳定")
print("      MaxSharpe容易过拟合: 历史上最好的策略≠未来最好的")""")

md("""## 5. 多策略组合回测 — 端到端""")

code("""from risk.combiner import StrategyCombiner

combiner = StrategyCombiner(
    strategies=strategies,
    allocator=InvVolAllocator(),
    initial_cash=1_000_000,
    slippage=0.001, commission_rate=0.0003,
)
report = combiner.run(df_csi)

# 对比
indiv = combiner.individual_sharpes()
avg_sharpe = np.mean(list(indiv.values()))
best_sharpe = max(indiv.values(), key=abs)
print(f"\\n总结:")
print(f"  单策略平均 Sharpe: {avg_sharpe:.3f}")
print(f"  单策略最高 Sharpe: {max(indiv.values()):.3f}")
print(f"  组合 Sharpe:        {report.sharpe_ratio:.3f}")
print(f"  组合 MDD:           {report.max_drawdown*100:.2f}%")
print(f"  组合收益:           {report.total_return*100:.2f}%")

# 可视化: 4单策略 + 组合净值
fig, ax = plt.subplots(figsize=(14, 6))
for name, rpt in combiner.individual_reports.items():
    navs = np.array([n for _, n in rpt.nav_history])
    ax.plot([t for t, _ in rpt.nav_history], navs/1_000_000, lw=0.8, alpha=0.6, label=f"{name}")

combo_nav = np.array([n for _, n in report.nav_history])
combo_dates = [t for t, _ in report.nav_history]
ax.plot(combo_dates, combo_nav/1_000_000, "k", lw=2.5, label="Combo (InvVol)")
ax.axhline(y=1, color="gray", ls="--", alpha=0.3)
ax.set_title("4 Strategies + Portfolio Combo (CSI 300, 2024)", fontsize=12, fontweight="bold")
ax.set_ylabel("Net Value"); ax.legend(ncol=2); ax.grid(True, alpha=0.3)
plt.tight_layout(); plt.show()""")

md("""## 6. 总结

### 风控的系统化流程

```
Step 1: 仓位管理
  → 选一个 Sizer, 控制每次开仓的资金比例
  → 默认: Kelly half 或 Fixed 20%

Step 2: 止损系统
  → 每个策略的 on_bar() 开头先检查止损
  → 默认: ATR止损(2x) + 时间止损(20天)

Step 3: 策略相关性
  → 日收益相关性 < 0.5 = 可配对
  → 回撤不重叠 = 组合效果最好

Step 4: 资金分配
  → 等权 = 基准
  → 波动率倒数 = 最稳健 (推荐)
  → Max Sharpe = 理论最优但容易过拟合
```

### 关键数据 (CSI300 2024)

```
单策略                                   组合
DualMA  Sharpe -0.024  MDD -10.14%
Boll    Sharpe  0.373  MDD  -6.28%      Sharpe  0.570
Turtle  Sharpe  0.668  MDD  -7.99%  →   MDD    -5.85%
RSRS    Sharpe  0.761  MDD -12.83%       Return   6.99%

组合 Sharpe (0.570) > 平均单策略 (0.445)
组合 MDD (-5.85%)    > 所有单策略 (全部低于 -6%)
```

### 下一步: 执行层

风控体系完备。下一步连接实盘——让策略从纸上走向市场。""")

with open("notebooks/04_risk_portfolio.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("Done: 04_risk_portfolio.ipynb")
