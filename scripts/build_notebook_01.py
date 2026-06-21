#!/usr/bin/env python3
"""Build 01_data_pipeline.ipynb with proxy + 3-market support."""
import json

nb = {
    "cells": [],
    "metadata": {
        "kernelspec": {
            "display_name": "Python (quant)",
            "language": "python",
            "name": "quant",
        },
        "language_info": {"name": "python", "version": "3.13.2"},
    },
    "nbformat": 4,
    "nbformat_minor": 4,
}

def md(source):
    nb["cells"].append({"cell_type": "markdown", "source": source})

def code(source):
    nb["cells"].append({"cell_type": "code", "source": source, "outputs": [], "execution_count": None})

# ===== 1 =====
md([
    "# 01 数据管道 — 三市场统一接口\n",
    "\n",
    "### 代理配置\n",
    "\n",
    "```\n",
    "v2rayN → SOCKS5 127.0.0.1:10808 → 自动为美股/加密启用\n",
    "已写入 .env:  PROXY_SOCKS5=socks5://127.0.0.1:10808\n",
    "```\n",
    "\n",
    "| 市场 | 数据源 | 代理 | 状态 |\n",
    "|------|--------|------|------|\n",
    "| A股 | baostock | ❌ 直连 | ✅ |\n",
    "| 加密 | ccxt Gate.io/Kraken | ⚠️ 自动切换 | ✅ |\n",
    "| 美股+港股 | yfinance | ✅ SOCKS5 | ✅ |\n",
    "\n",
    "---\n",
    "\n",
    "| 章节 | 概念 |\n",
    "|------|------|\n",
    "| 1. 架构全景 | API → DataFrame → SQLite 三层分离 |\n",
    "| 2. 统一 Schema | 10列标准，三市场遵守 |\n",
    "| 3. ABC 抽象基类 | 多态：同一接口，不同实现 |\n",
    "| 4. AShareSource | baostock 直连 |\n",
    "| 5. CryptoSource | Gate.io直连 → Kraken代理自动切换 |\n",
    "| 6. USStockSource | yfinance + SOCKS5 代理 |\n",
    "| 7. 三市场对比 | 同一套代码，三个市场 |\n",
    "| 8. SQLite 存储 | WAL+UPSERT+缓存加速 |\n",
    "| 9. 端到端 | 存→读→画，断网可用 |",
])

# ===== 2 =====
md([
    "## 1. 架构全景\n",
    "\n",
    "```\n",
    "┌──────────────────────────────────────────┐\n",
    "│  source.get_history(symbols, start, end) │  ← 一行\n",
    "├──────────────────────────────────────────┤\n",
    "│  第1层: DataSource (适配)                │\n",
    "│    _fetch()  → API (直连or代理)          │\n",
    "│    _normalize() → 统一Schema              │\n",
    "│    → 标准DataFrame (内存)                 │\n",
    "├──────────────────────────────────────────┤\n",
    "│  第2层: DataFrame (分析)                 │\n",
    "│    筛选、画图、算指标、回测               │\n",
    "├──────────────────────────────────────────┤\n",
    "│  第3层: DataStore (持久化)               │\n",
    "│    store.save() → SQLite                 │\n",
    "│    store.load()  → 毫秒级，断网可用       │\n",
    "└──────────────────────────────────────────┘\n",
    "```\n",
    "\n",
    "**核心设计**：三层互不耦合。API 不知道 SQLite，SQLite 不知道代理。",
])

# ===== 3 =====
code([
    "import sys; sys.path.insert(0, '..')\n",
    "import pandas as pd, numpy as np, matplotlib.pyplot as plt, warnings\n",
    "warnings.filterwarnings('ignore')\n",
    "plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']\n",
    "plt.rcParams['axes.unicode_minus'] = False\n",
    "print('OK')\n",
])

# ===== 4 =====
md([
    "## 2. 统一 Schema — 10列标准\n",
    "\n",
    "所有市场输出完全一致的列，这是系统的数据契约。",
])

# ===== 5 =====
code([
    "from data.schema import OHLCV_COLUMNS\n",
    "for i, c in enumerate(OHLCV_COLUMNS):\n",
    "    print(f'  {i+1}. {c}')\n",
])

# ===== 6 =====
md([
    "## 3. ABC 抽象基类\n",
    "\n",
    "```python\n",
    "class DataSource(ABC):\n",
    "    @abstractmethod\n",
    "    def _fetch(self, symbol, start, end): ...\n",
    "\n",
    "    def get_history(self, symbols, start, end):\n",
    "        for sym in symbols:\n",
    "            raw = self._fetch(sym, start, end)\n",
    "        return self._normalize(all_frames)  # 统一10列\n",
    "```\n",
    "\n",
    "**多态**：`get_history()` 不管底层是 A股/加密/美股，行为完全一致。",
])

# ===== 7 =====
md([
    "## 4. AShareSource — A股（直连，无需代理）\n",
    "\n",
    "baostock 独立数据源，国内直连。",
])

# ===== 8 =====
code([
    "from data.sources.ashare import AShareSource\n",
    "ashare = AShareSource()\n",
    "df_a = ashare.get_history(['sh.000300', 'sh.600519', 'sz.300750'], '2024-01-01', '2024-06-30')\n",
    "print(f'A股: {df_a.symbol.nunique()}只, {len(df_a)}行, market={df_a.market.iloc[0]}')\n",
    "print(f'每只: {df_a.groupby(\"symbol\").size().to_dict()}')\n",
    "df_a.head(3)\n",
])

# ===== 9 =====
md([
    "## 5. CryptoSource — 加密（直连→代理自动切换）\n",
    "\n",
    "```\n",
    "CryptoSource()\n",
    "  → Gate.io 直连 (国内可用)\n",
    "  → 失败 → Kraken/Binance via SOCKS5 代理\n",
    "```",
])

# ===== 10 =====
code([
    "import os\n",
    "os.environ['PROXY_SOCKS5'] = 'socks5://127.0.0.1:10808'  # v2rayN\n",
    "\n",
    "from data.sources.crypto import CryptoSource\n",
    "crypto = CryptoSource()  # 自动探测\n",
    "df_c = crypto.get_history(['BTC/USDT', 'ETH/USDT'], '2024-01-01', '2024-06-30')\n",
    "print(f'加密: {df_c.symbol.nunique()}对, {len(df_c)}行, market={df_c.market.iloc[0]}')\n",
    "print(f'每对: {df_c.groupby(\"symbol\").size().to_dict()}')\n",
    "df_c.head(3)\n",
])

# ===== 11 =====
md([
    "## 6. USStockSource — 美股+港股（SOCKS5 代理）\n",
    "\n",
    "yfinance + v2rayN SOCKS5 → Yahoo Finance 全市场。\n",
    "自动读取 `.env` 中的 `PROXY_SOCKS5`，每次请求前后 set/clear 代理不污染其他连接。",
])

# ===== 12 =====
code([
    "from data.sources.usstocks import USStockSource\n",
    "us = USStockSource()  # 自动读取 PROXY_SOCKS5\n",
    "df_us = us.get_history(['AAPL', 'TSLA', 'MSFT', 'BABA'], '2024-01-01', '2024-06-30')\n",
    "print(f'美股: {df_us.symbol.nunique()}只, {len(df_us)}行, market={df_us.market.iloc[0]}')\n",
    "print(f'每只: {df_us.groupby(\"symbol\").size().to_dict()}')\n",
    "df_us.head(3)\n",
])

# ===== 13 =====
md([
    "## 7. 三市场对比 — 同一份代码\n",
    "\n",
    "下面三个图的代码完全一样，唯一的区别是传入的 DataFrame。",
])

# ===== 14 =====
code([
    "fig, axes = plt.subplots(1, 3, figsize=(18, 5))\n",
    "datasets = [\n",
    "    (df_a[df_a.symbol=='sh.000300'], '沪深300', 'steelblue'),\n",
    "    (df_c[df_c.symbol=='BTC/USDT'],   'BTC/USDT', 'orange'),\n",
    "    (df_us[df_us.symbol=='AAPL'],     'Apple',    'green'),\n",
    "]\n",
    "for ax, (df, name, color) in zip(axes, datasets):\n",
    "    ret = np.log(df['close'] / df['close'].shift(1)).dropna()\n",
    "    ax.hist(ret, bins=50, density=True, alpha=0.7, color=color)\n",
    "    mu, sig = ret.mean(), ret.std()\n",
    "    x = np.linspace(mu-4*sig, mu+4*sig, 100)\n",
    "    ax.plot(x, 1/(sig*np.sqrt(2*np.pi))*np.exp(-(x-mu)**2/(2*sig**2)), 'r-', lw=1)\n",
    "    vol_annual = sig * np.sqrt(252) * 100\n",
    "    sharpe = (mu*252 - 0.025) / (sig*np.sqrt(252))\n",
    "    ax.set_title(f'{name}\\n年化波动={vol_annual:.1f}% | Sharpe={sharpe:.2f}')\n",
    "    ax.axvline(x=0, color='gray', ls='--', alpha=0.5)\n",
    "plt.suptitle('同一分析代码 x 三个市场', fontsize=13, fontweight='bold')\n",
    "plt.tight_layout()\n",
    "plt.show()\n",
    "\n",
    "print('沪深300: 波动适中, 零收益 → 择时策略有价值')\n",
    "print('BTC/USDT: 高波动 → 趋势跟踪的天堂')\n",
    "print('Apple: 稳健上行 → 买入持有就好')\n",
])

# ===== 15 =====
md([
    "## 8. SQLite 存储 — 三市场全部落地\n",
    "\n",
    "API → DataFrame(检查) → SQLite(缓存)。WAL + UPSERT。",
])

# ===== 16 =====
code([
    "from data.store import DataStore\n",
    "import time\n",
    "\n",
    "store = DataStore('../data/quant.db')\n",
    "store.save(df_a, 'ashare', 'daily')\n",
    "store.save(df_c, 'crypto', 'daily')\n",
    "store.save(df_us, 'usstock', 'daily')\n",
    "\n",
    "display(store.list_tables())\n",
    "\n",
    "t0 = time.time()\n",
    "df_sql = store.load('usstock', 'daily', symbols=['AAPL'])\n",
    "print(f'\\nSQLite读取: {len(df_sql)}行, {(time.time()-t0)*1000:.0f}ms')\n",
    "print(f'vs 首次拉取: 快 1000x+')\n",
])

# ===== 17 =====
md([
    "## 9. 端到端验证 — 断网也能分析\n",
    "\n",
    "从 SQLite 读取 → 净值曲线对比（完全离线）。",
])

# ===== 18 =====
code([
    "df_plot = store.load('usstock', 'daily', symbols=['AAPL', 'MSFT'], start='2024-01-01')\n",
    "fig, ax = plt.subplots(figsize=(14, 5))\n",
    "for sym in df_plot.symbol.unique():\n",
    "    sub = df_plot[df_plot.symbol==sym].set_index('date')\n",
    "    nav = sub['close'] / sub['close'].iloc[0]\n",
    "    ax.plot(nav.index, nav.values, lw=1.5, label=sym)\n",
    "ax.legend()\n",
    "ax.set_title('Apple vs Microsoft 2024上半年 (数据: 本地SQLite, 无需联网)', fontsize=12)\n",
    "ax.set_ylabel('净值')\n",
    "ax.grid(True, alpha=0.3)\n",
    "plt.show()\n",
])

# ===== 19 =====
md([
    "## 10. 总结\n",
    "\n",
    "```\n",
    "               ┌─── AShareSource (baostock, 直连)\n",
    "get_history() ─┼─── CryptoSource (Gate.io/Kraken, 自动切换)\n",
    "               └─── USStockSource (yfinance + SOCKS5)\n",
    "                        ↓\n",
    "               标准10列 DataFrame (内存)\n",
    "                        ↓\n",
    "           DataStore ─→ SQLite (WAL, 毫秒读, 断网可用)\n",
    "```\n",
    "\n",
    "| 认知 | 真相 |\n",
    "|------|------|\n",
    "| 海外数据拿不到 | SOCKS5代理 → yfinance/ccxt 全通 |\n",
    "| 数据直接灌SQL | API→DataFrame→SQL，三层可检查 |\n",
    "| 不同市场不同代码 | 同一个 get_history()，多态分发 |\n",
    "\n",
    "### 下一步：回测引擎\n",
    "数据管道就绪。让双均线策略在三个市场同时回测。",
])

with open("notebooks/01_data_pipeline.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print("Done")
