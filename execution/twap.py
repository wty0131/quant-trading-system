"""
TWAP/VWAP 拆单执行算法 — 从长城证券 QMT algorithms/ 适配

QMT内置了8个券商算法 (睿金/中信建投/中金/中信/方正/国信/华创/申万/浙商)

TWAP (Time-Weighted Average Price):
  将大单按时间均分 → 降低对市场的冲击 → 避免一次性吃掉流动性

VWAP (Volume-Weighted Average Price):
  按历史成交量分布加权拆单 → 更精细地模拟自然交易

用途:
  1. 将策略产出的 SignalEvent → 拆成多个小 OrderEvent
  2. 配合 OrderManager 按时间片逐步发送
  3. 实盘中配合 QMTBroker 调用 xtquant 下单
"""

from datetime import datetime, timedelta
from dataclasses import dataclass, field


@dataclass
class OrderSlice:
    """一个时间片订单"""
    time: str          # "09:30"
    quantity: int
    order_type: str = "MKT"


class TWAPExecutor:
    """
    TWAP 拆单执行器

    用法:
        twap = TWAPExecutor()
        slices = twap.slice(10000, "09:30", "15:00", 5)
        # → 66个slice，每个约151股
    """

    def slice(
        self,
        total_qty: int,
        start_time: str = "09:30",
        end_time: str = "15:00",
        interval_minutes: int = 5,
    ) -> list[OrderSlice]:
        """
        按时间等分拆单

        Args:
            total_qty:        总委托量
            start_time:       开始时间
            end_time:         结束时间
            interval_minutes: 时间片间隔（分钟）

        Returns:
            OrderSlice 列表
        """
        start = self._parse_time(start_time)
        end = self._parse_time(end_time)

        # 计算时间片数量
        total_minutes = (end - start).seconds // 60
        num_slices = total_minutes // interval_minutes
        if num_slices <= 0:
            return [OrderSlice(time=start_time, quantity=total_qty)]

        # 每片数量（整数均分，余数放最后一片）
        base_qty = total_qty // num_slices
        remainder = total_qty % num_slices

        slices = []
        current = start
        for i in range(num_slices):
            qty = base_qty + (1 if i == num_slices - 1 else 0) * remainder
            if qty <= 0:
                continue
            time_str = current.strftime("%H:%M")
            slices.append(OrderSlice(time=time_str, quantity=qty))
            current += timedelta(minutes=interval_minutes)

        # 验证总量
        assert sum(s.quantity for s in slices) == total_qty, "切片总量不匹配"

        return slices

    @staticmethod
    def _parse_time(t: str) -> datetime:
        h, m = map(int, t.split(":"))
        return datetime(2024, 1, 1, h, m)


class VWAPExecutor:
    """
    VWAP 拆单 — 按历史成交量分布加权

    原理: 统计该股票历史上每个时间片的成交量占比 → 按比例分配订单量
    例: 如果历史上 10:00-10:05 占全天成交量的 8% → 分配 8% 的订单量
    """

    def slice(
        self,
        total_qty: int,
        volume_profile: dict[str, float],  # {"09:30": 0.05, "09:35": 0.04, ...}
        start_time: str = "09:30",
    ) -> list[OrderSlice]:
        """
        Args:
            total_qty:      总委托量
            volume_profile: 历史成交量分布 {时间片: 占比}
            start_time:     起始时间

        Returns:
            OrderSlice 列表
        """
        # 按时间排序
        ordered = sorted(volume_profile.items())

        slices = []
        remaining_qty = total_qty
        allocated = 0

        for i, (time_str, weight) in enumerate(ordered):
            if time_str < start_time:
                continue
            if i == len(ordered) - 1:
                # 最后一片：全部剩余（防舍入误差）
                qty = remaining_qty
            else:
                qty = int(total_qty * weight)
            if qty > 0:
                slices.append(OrderSlice(time=time_str, quantity=qty))
                allocated += qty
                remaining_qty = total_qty - allocated

        return slices

    @staticmethod
    def estimate_profile(
        df_1min,  # 过去N天的1分钟K线
        interval_minutes: int = 5,
    ) -> dict[str, float]:
        """
        从历史1分钟K线估算成交量分布

        Args:
            df_1min: 1分钟K线 DataFrame
            interval_minutes: 聚合粒度

        Returns:
            {时间片: 成交量占比}
        """
        if df_1min.empty:
            return {}

        df = df_1min.copy()
        df["time"] = pd.to_datetime(df["date"]).dt.strftime("%H:%M")
        df["group"] = (
            pd.to_datetime(df["date"]).dt.hour * 60
            + pd.to_datetime(df["date"]).dt.minute
        ) // interval_minutes

        profile = df.groupby("group")["volume"].sum()
        profile = profile / profile.sum()
        return {f"{g*interval_minutes//60:02d}:{g*interval_minutes%60:02d}": float(v)
                for g, v in profile.items()}


import pandas as pd  # noqa: E402
