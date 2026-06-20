"""
A 股数据源 — 基于 baostock (baostock.com)

特点：
  - 独立数据源，不依赖东方财富
  - 无需注册/Token
  - 覆盖沪深全部股票 + 指数
  - 支持前/后复权

封装要点（踩坑总结）：
  - baostock 单次查询约返回 500 条（≈2年日线），按年分片
  - login/logout 成对调用，避免连接泄漏
  - 请求间 sleep 0.3s 控制频率
"""

import time
import pandas as pd
import baostock as bs

from .base import DataSource


class AShareSource(DataSource):
    """A股数据源 — baostock"""

    market = "ashare"
    # 支持的 K 线周期
    FREQ_MAP = {
        "daily": "d",
        "weekly": "w",
        "monthly": "m",
    }

    def __init__(self, adjust: str = "2"):
        """
        Args:
            adjust: 复权方式
                1 = 后复权
                2 = 前复权（默认）
                3 = 不复权
        """
        self.adjust = adjust

    def _fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        """
        从 baostock 获取单只股票/指数日线

        symbol 格式:
          指数: sh.000300 (沪深300), sz.399001 (深证成指)
          沪股: sh.600519 (贵州茅台)
          深股: sz.300750 (宁德时代)
        """
        sy, ey = int(start[:4]), int(end[:4])
        all_rows = []

        bs.login()
        try:
            for y in range(sy, ey + 1):
                seg_start = start if y == sy else f"{y}-01-01"
                seg_end = end if y == ey else f"{y}-12-31"

                rs = bs.query_history_k_data_plus(
                    symbol,
                    "date,open,high,low,close,volume,amount",
                    start_date=seg_start,
                    end_date=seg_end,
                    frequency="d",
                    adjustflag=self.adjust,
                )

                if rs.error_code != "0":
                    continue

                while rs.next():
                    all_rows.append(rs.get_row_data())

                time.sleep(0.3)

            if not all_rows:
                return pd.DataFrame()

            df = pd.DataFrame(
                all_rows,
                columns=["date", "open", "high", "low", "close", "volume", "amount"],
            )

            return df

        finally:
            bs.logout()

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取全市场股票列表（沪深）
        返回: DataFrame with [code, name, type]
        """
        bs.login()
        try:
            # 沪市
            rs_sh = bs.query_stock_basic(code_name="沪市A股")
            sh_stocks = []
            while rs_sh.next():
                sh_stocks.append(rs_sh.get_row_data())

            # 深市
            rs_sz = bs.query_stock_basic(code_name="深市A股")
            sz_stocks = []
            while rs_sz.next():
                sz_stocks.append(rs_sz.get_row_data())

            sh_df = pd.DataFrame(sh_stocks, columns=["code", "name", "type"])
            sz_df = pd.DataFrame(sz_stocks, columns=["code", "name", "type"])
            df = pd.concat([sh_df, sz_df], ignore_index=True)
            df["market"] = "ashare"
            return df
        finally:
            bs.logout()
