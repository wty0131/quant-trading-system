"""
A股全市场股票池 — 5000+ 只, 从 baostock 实时获取

用法:
  from data.ashare_pool import fetch_all_stocks
  stocks = fetch_all_stocks()  # {名称 (sh.000001): sh.000001, ...}

缓存: 首次调用 ~10s, 之后从内存读取
"""

ALL_STOCKS_CACHE: dict[str, str] | None = None


def fetch_all_stocks() -> dict[str, str]:
    """
    从 baostock 获取全市场 A 股列表 (~5000 只)
    缓存: 首次 ~10s, 之后内存秒读.
    过滤: ST/退市
    """
    global ALL_STOCKS_CACHE
    if ALL_STOCKS_CACHE is not None:
        return ALL_STOCKS_CACHE

    import baostock as bs
    bs.login()
    try:
        rs = bs.query_stock_basic()
        result = {}
        while rs.next():
            row = rs.get_row_data()
            code, name, _, _, stype, status = row
            if stype == '1' and status == '1' and 'ST' not in name and '退' not in name:
                result[f'{name} ({code})'] = code
        ALL_STOCKS_CACHE = result
        return result
    finally:
        bs.logout()


def get_code_list() -> list[str]:
    """返回纯代码列表"""
    return list(fetch_all_stocks().values())
