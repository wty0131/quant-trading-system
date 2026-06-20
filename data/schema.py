"""
统一数据 Schema — 所有市场数据源必须输出的标准格式

列名、类型、约束定义在这里，整个系统以此为契约。
"""

# 标准 OHLCV 列（加上元数据）
OHLCV_COLUMNS = [
    "symbol",       # 品种代码，如 sh.000300, BTC/USDT
    "date",         # 交易日日期
    "open",         # 开盘价
    "high",         # 最高价
    "low",          # 最低价
    "close",        # 收盘价
    "volume",       # 成交量
    "amount",       # 成交额（加密/美股可为0）
    "market",       # 市场标识: ashare / crypto / usstock
    "interval",     # K线周期: daily / weekly / 1h 等
]

OHLCV_DTYPES = {
    "symbol":   "string",
    "date":     "datetime64[ns]",
    "open":     "float64",
    "high":     "float64",
    "low":      "float64",
    "close":    "float64",
    "volume":   "float64",
    "amount":   "float64",
    "market":   "string",
    "interval": "string",
}
