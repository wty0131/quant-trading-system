"""
执行模拟 — 撮合成交、滑点、手续费

模拟交易成本对回测结果的影响：
  - 滑点 (slippage)：买入时成交价可能略高于 bar.close
  - 手续费 (commission)：A股万三，加密 0.1%
"""

from .event import OrderEvent, FillEvent, Direction


class ExecutionHandler:
    """
    模拟执行引擎

    Args:
        slippage:        滑点比例（默认 0.001 = 0.1%）
                        买入: price = close * (1 + slippage)
                        卖出: price = close * (1 - slippage)
        commission_rate: 手续费率  （默认 0.0003 = 万三）
    """

    def __init__(self, slippage: float = 0.001, commission_rate: float = 0.0003):
        self.slippage = slippage
        self.commission_rate = commission_rate

    def execute(self, order: OrderEvent, bar: dict) -> FillEvent:
        """
        模拟成交

        Args:
            order: 待执行订单
            bar:   当前K线数据（用于取价格）

        Returns:
            FillEvent — 成交回报
        """
        close = bar["close"] if isinstance(bar, dict) else float(bar.close)

        if order.direction == Direction.LONG:
            fill_price = close * (1 + self.slippage)
        else:
            fill_price = close * (1 - self.slippage)

        commission = fill_price * order.quantity * self.commission_rate

        return FillEvent(
            timestamp=order.timestamp,
            symbol=order.symbol,
            direction=order.direction,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
        )
