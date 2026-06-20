#!/usr/bin/env python
"""Update notebook cells to use baostock with single-login strategy."""
import json

with open('notebooks/00_data_exploration.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# === Cell 2: Imports + baostock wrapper ===
nb['cells'][2]['source'] = [
    'import pandas as pd\n',
    'import numpy as np\n',
    'import matplotlib.pyplot as plt\n',
    'import warnings\n',
    'import time\n',
    'warnings.filterwarnings("ignore")\n',
    '\n',
    '# --- 数据源 ---\n',
    'import baostock as bs\n',
    'HAS_AKSHARE = False\n',
    'try:\n',
    '    import akshare as ak; HAS_AKSHARE = True\n',
    'except ImportError:\n',
    '    pass\n',
    '\n',
    '# --- 中文字体 ---\n',
    'plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]\n',
    'plt.rcParams["axes.unicode_minus"] = False\n',
    'plt.rcParams["figure.dpi"] = 100\n',
    'plt.rcParams["savefig.dpi"] = 150\n',
    '\n',
    '# --- baostock 批量数据获取（单次login，多段查询，避免连接断开）---\n',
    'def _query_one(symbol, start, end, adjust):\n',
    '    """单次查询，返回数据行列表"""\n',
    '    rs = bs.query_history_k_data_plus(\n',
    '        symbol, "date,open,high,low,close,volume,amount",\n',
    '        start_date=start, end_date=end, frequency="d", adjustflag=adjust)\n',
    '    if rs.error_code != "0":\n',
    '        return []\n',
    '    rows = []\n',
    '    while rs.next():\n',
    '        rows.append(rs.get_row_data())\n',
    '    return rows\n',
    '\n',
    'def fetch_baostock(symbol, start, end, adjust="2"):\n',
    '    """\n',
    '    从 baostock (baostock.com) 获取真实A股日线数据\n',
    '    严格login一次、logout一次，避免连续断连\n',
    '    """\n',
    '    bs.login()\n',
    '    try:\n',
    '        # 按年切分（baostock单次约返回500条，约2年）\n',
    '        sy, ey = int(start[:4]), int(end[:4])\n',
    '        all_rows = []\n',
    '        for y in range(sy, ey + 1):\n',
    '            seg_start = start if y == sy else f"{y}-01-01"\n',
    '            seg_end   = end   if y == ey else f"{y}-12-31"\n',
    '            rows = _query_one(symbol, seg_start, seg_end, adjust)\n',
    '            if rows:\n',
    '                all_rows.extend(rows)\n',
    '            time.sleep(0.3)  # 节制请求频率\n',
    '        if not all_rows:\n',
    '            raise Exception("无数据")\n',
    '        df = pd.DataFrame(all_rows, columns=["date","open","high","low","close","volume","amount"])\n',
    '        for c in ["open","high","low","close","volume","amount"]:\n',
    '            df[c] = pd.to_numeric(df[c], errors="coerce")\n',
    '        df["date"] = pd.to_datetime(df["date"])\n',
    '        df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)\n',
    '        return df\n',
    '    finally:\n',
    '        bs.logout()\n',
    '\n',
    'print(f"pandas {pd.__version__} | numpy {np.__version__}")\n',
    'print(f"数据源: baostock (真实A股) + akshare ({\"备用\" if HAS_AKSHARE else \"-\"})")',
]

# === Cell 4: CSI 300 ===
nb['cells'][4]['source'] = [
    '# 从 baostock 获取沪深300指数真实日线数据\n',
    'print("正在从 baostock 获取沪深300指数 ...")\n',
    'df_index = fetch_baostock("sh.000300", "2020-01-01", "2025-06-20")\n',
    'print(f"✓ 已获取: {len(df_index)} 条, {df_index.date.min().date()} ~ {df_index.date.max().date()}")\n',
    'print(f"来源: baostock.org 真实沪深300行情")\n',
    'df_index.head(10)\n',
]

# === Cell 16: Individual stocks ===
nb['cells'][16]['source'] = [
    '# 从 baostock 获取个股真实日线数据\n',
    'stocks_map = [\n',
    '    ("贵州茅台", "sh.600519"),\n',
    '    ("宁德时代", "sz.300750"),\n',
    '    ("招商银行", "sh.600036"),\n',
    '    ("比亚迪",   "sz.002594"),\n',
    '    ("中国平安", "sh.601318"),\n',
    ']\n',
    '\n',
    'close_prices = pd.DataFrame()\n',
    'for name, symbol in stocks_map:\n',
    '    print(f"  获取 {name} ({symbol}) ...", end=" ")\n',
    '    try:\n',
    '        df_stock = fetch_baostock(symbol, "2021-01-01", "2025-06-20")\n',
    '        df_stock = df_stock.set_index("date")\n',
    '        close_prices[name] = df_stock["close"]\n',
    '        print(f"OK {len(df_stock)}条")\n',
    '    except Exception as e:\n',
    '        print(f"失败: {e}")\n',
    '\n',
    'print(f"\\n成功: {len(close_prices.columns)}/{len(stocks_map)} 只, 形状: {close_prices.shape}")\n',
    'close_prices.head()\n',
]

with open('notebooks/00_data_exploration.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print("Done")
