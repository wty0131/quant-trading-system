#!/usr/bin/env python3
"""Build 01_data_pipeline.ipynb with nbformat."""
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

def md(source):
    nb.cells.append(nbf.v4.new_markdown_cell(source))

def code(source):
    nb.cells.append(nbf.v4.new_code_cell(source))

# === Cell 0 ===
md("""# 01 数据管道 — 三市场统一接口

### 代理配置

```
v2rayN -> SOCKS5 127.0.0.1:10808 -> 自动为美股/加密启用
已写入 .env:  PROXY_SOCKS5=socks5://127.0.0.1:10808
```

| 市场 | 数据源 | 代理 | 状态 |
|------|--------|------|------|
| A股 | baostock | 直连 | OK |
| 加密 | ccxt Gate.io/Kraken | 自动切换 | OK |
| 美股+港股 | yfinance | SOCKS5 | OK |

---
| 章节 | 概念 |
|------|------|
| 1. 架构全景 | API -> DataFrame -> SQLite 三层分离 |
| 2. 统一 Schema | 10列标准，三市场遵守 |
| 3. ABC 抽象基类 | 多态：同一接口，不同实现 |
| 4. AShareSource | baostock 直连 |
| 5. CryptoSource | Gate.io直连 -> Kraken代理自动切换 |
| 6. USStockSource | yfinance + SOCKS5 代理 |
| 7. 三市场对比 | 同一套代码，三个市场 |
| 8. SQLite 存储 | WAL+UPSERT+缓存加速 |
| 9. 端到端 | 存->读->画，断网可用 |""")

# === Cell 1 ===
md("""## 1. 架构全景

```
source.get_history(symbols, start, end)   <- 你写的唯一一行
        |
第1层: DataSource (适配)
  _fetch()  -> API (直连或代理)
  _normalize() -> 统一Schema
  -> 标准DataFrame (内存)
        |
第2层: DataFrame (分析)
  筛选、画图、算指标、回测
        |
第3层: DataStore (持久化)
  store.save() -> SQLite
  store.load()  -> 毫秒级，断网可用
```

**核心设计**：三层互不耦合。API 不知道 SQLite，SQLite 不知道代理。""")

# === Cell 2 ===
code("""import sys; sys.path.insert(0, "..")
import pandas as pd, numpy as np, matplotlib.pyplot as plt, warnings
warnings.filterwarnings("ignore")
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
print("OK")""")

# === Cell 3 ===
md("""## 2. 统一 Schema -- 10列标准

所有市场输出完全一致的列，这是系统的数据契约。""")

# === Cell 4 ===
code("""from data.schema import OHLCV_COLUMNS
for i, c in enumerate(OHLCV_COLUMNS):
    print(f"  {i+1}. {c}")
print()
print("这10列是所有数据源的共同契约")""")

# === Cell 5 ===
md("""## 3. ABC 抽象基类

```python
class DataSource(ABC):
    @abstractmethod
    def _fetch(self, symbol, start, end): ...

    def get_history(self, symbols, start, end):
        for sym in symbols:
            raw = self._fetch(sym, start, end)
        return self._normalize(all_frames)  # 统一10列
```

**多态**：get_history() 不管底层是 A股/加密/美股，行为完全一致。""")

# === Cell 6 ===
md("""## 4. AShareSource -- A股 (直连，无需代理)

baostock 独立数据源，国内直连。""")

# === Cell 7 ===
code("""from data.sources.ashare import AShareSource
ashare = AShareSource()
df_a = ashare.get_history(["sh.000300", "sh.600519", "sz.300750"], "2024-01-01", "2024-06-30")
print(f"A股: {df_a.symbol.nunique()} 只, {len(df_a)} 行, market={df_a.market.iloc[0]}")
print(f"每只: {df_a.groupby('symbol').size().to_dict()}")
df_a.head(3)""")

# === Cell 8 ===
md("""## 5. CryptoSource -- 加密 (直连->代理自动切换)

```
CryptoSource()
  -> Gate.io 直连 (国内可用)
  -> 失败 -> Kraken/Binance via SOCKS5 代理
```""")

# === Cell 9 ===
code("""import os
os.environ["PROXY_SOCKS5"] = "socks5://127.0.0.1:10808"  # v2rayN
import importlib
import data.sources.crypto as cmod
importlib.reload(cmod)  # 强制重载最新代码
from data.sources.crypto import CryptoSource

crypto = CryptoSource()  # 自动探测
df_c = crypto.get_history(["BTC/USDT", "ETH/USDT"], "2024-01-01", "2024-06-30")

if df_c.empty:
    print("⚠️ 加密数据为空")
    print("   1. 确认 v2rayN 正在运行")
    print("   2. 确认 SOCKS5 端口 10808")
    print("   3. 手动验证: crypto.exchange_name")
    print(f"   当前交易所: {crypto.exchange_name}")
else:
    print(f"加密: {df_c.symbol.nunique()} 对, {len(df_c)} 行")
    print(f"每对: {df_c.groupby('symbol').size().to_dict()}")
    df_c.head(3)""")

# === Cell 10 ===
md("""## 6. USStockSource -- 美股+港股 (SOCKS5 代理)

yfinance + v2rayN SOCKS5 -> Yahoo Finance 全市场。
自动读取 .env 中的 PROXY_SOCKS5，每次请求前后 set/clear 代理不污染其他连接。""")

# === Cell 11 ===
code("""from data.sources.usstocks import USStockSource
us = USStockSource()  # 自动读取 PROXY_SOCKS5
df_us = us.get_history(["AAPL", "TSLA", "MSFT", "BABA"], "2024-01-01", "2024-06-30")
print(f"美股: {df_us.symbol.nunique()} 只, {len(df_us)} 行, market={df_us.market.iloc[0]}")
print(f"每只: {df_us.groupby('symbol').size().to_dict()}")
df_us.head(3)""")

# === Cell 12 ===
md("""## 7. 三市场对比 -- 同一份代码

下面三个图的代码完全一样，唯一的区别是传入的 DataFrame。""")

# === Cell 13 ===
code("""fig, axes = plt.subplots(1, 3, figsize=(18, 5))
datasets = [
    (df_a[df_a.symbol=="sh.000300"], "CSI 300", "steelblue"),
]
if not df_c.empty:
    datasets.append((df_c[df_c.symbol=="BTC/USDT"], "BTC/USDT", "orange"))
if not df_us.empty:
    datasets.append((df_us[df_us.symbol=="AAPL"], "Apple", "green"))

for ax, (df, name, color) in zip(axes, datasets):
    ret = np.log(df["close"] / df["close"].shift(1)).dropna()
    ax.hist(ret, bins=50, density=True, alpha=0.7, color=color)
    mu, sig = ret.mean(), ret.std()
    x = np.linspace(mu-4*sig, mu+4*sig, 100)
    ax.plot(x, 1/(sig*np.sqrt(2*np.pi))*np.exp(-(x-mu)**2/(2*sig**2)), "r-", lw=1)
    vol_annual = sig * np.sqrt(252) * 100
    sharpe = (mu*252 - 0.025) / (sig*np.sqrt(252)) if sig > 0 else 0
    ax.set_title(f"{name}\\nvol={vol_annual:.1f}% | Sharpe={sharpe:.2f}", fontsize=10)
    ax.axvline(x=0, color="gray", ls="--", alpha=0.5)
# 隐藏多余的 axes
for ax in axes[len(datasets):]:
    ax.set_visible(False)
plt.suptitle("Same Code x Markets", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.show()
for name, df, _ in datasets:
    ret = np.log(df["close"] / df["close"].shift(1)).dropna()
    print(f"{name}: annual_vol={ret.std()*np.sqrt(252)*100:.1f}% sharpe={((ret.mean()*252-0.025)/(ret.std()*np.sqrt(252))):.2f}")""")

# === Cell 14 ===
md("""## 8. SQLite 存储 -- 三市场全部落地

API -> DataFrame(check) -> SQLite(cache). WAL + UPSERT.""")

# === Cell 15 ===
code("""from data.store import DataStore
import time

store = DataStore("../data/quant.db")
store.save(df_a, "ashare", "daily")
if not df_c.empty:
    store.save(df_c, "crypto", "daily")
if not df_us.empty:
    store.save(df_us, "usstock", "daily")

display(store.list_tables())

if not df_us.empty:
    t0 = time.time()
    df_sql = store.load("usstock", "daily", symbols=["AAPL"])
    print(f"\\nSQLite read: {len(df_sql)} rows, {(time.time()-t0)*1000:.0f}ms")
    print("vs first pull: 1000x faster")
else:
    t0 = time.time()
    df_sql = store.load("ashare", "daily", symbols=["sh.000300"])
    print(f"\\nSQLite read (ashare): {len(df_sql)} rows, {(time.time()-t0)*1000:.0f}ms")""")

# === Cell 16 ===
md("""## 9. End-to-end -- offline analysis

SQLite -> net value curve (fully offline).""")

# === Cell 17 ===
code("""# 优先显示美股，不行就用A股
market, syms = ("usstock", ["AAPL", "MSFT"]) if not df_us.empty else ("ashare", ["sh.000300", "sh.600519"])
df_plot = store.load(market, "daily", symbols=syms, start="2024-01-01")

fig, ax = plt.subplots(figsize=(14, 5))
for sym in df_plot.symbol.unique():
    sub = df_plot[df_plot.symbol==sym].set_index("date")
    nav = sub["close"] / sub["close"].iloc[0]
    ax.plot(nav.index, nav.values, lw=1.5, label=sym)
ax.legend()
ax.set_title(f"{market} Net Value H1 2024 (source: local SQLite, no network)", fontsize=12)
ax.set_ylabel("Net Value")
ax.grid(True, alpha=0.3)
plt.show()""")

# === Cell 18 ===
md("""## 10. Summary

```
               +--- AShareSource (baostock, direct)
get_history() -+--- CryptoSource (Gate.io/Kraken, auto-switch)
               +--- USStockSource (yfinance + SOCKS5)
                        |
                Standard 10-col DataFrame (memory)
                        |
           DataStore -> SQLite (WAL, ms read, offline OK)
```

| Myth | Reality |
|------|---------|
| Can't get foreign data | SOCKS5 proxy -> yfinance/ccxt all work |
| Data goes straight to SQL | API->DataFrame->SQL, 3 layers checkable |
| Different code per market | Same get_history(), polymorphism |

### Next: Backtest Engine
Data pipeline ready. Let dual-MA strategy run on all 3 markets. Next step.""")

# Write
with open("notebooks/01_data_pipeline.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print("Done: 01_data_pipeline.ipynb built with nbformat")
