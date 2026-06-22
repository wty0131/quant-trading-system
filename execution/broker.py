"""
Broker 抽象基类 — 券商统一接口

设计模式: 与 DataSource 一样——定义契约，子类各实现。

核心方法:
  submit_order()    — 提交订单
  get_order_status() — 查询订单状态
  cancel_order()     — 撤单
  get_positions()    — 当前持仓
  get_balance()      — 账户余额
"""

from abc import ABC, abstractmethod
from datetime import datetime


class Broker(ABC):
    """
    券商抽象基类

    三种实现:
      PaperBroker — 模拟成交，用实时价格 (立刻可用)
      CCXTBroker  — 加密实盘 via ccxt (需代理)
      QMTBroker   — A股实盘 via xtquant (需券商开通)
    """

    def __init__(self, initial_cash: float = 1_000_000):
        self._initial_cash = initial_cash

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        direction: str,        # 'LONG' or 'EXIT'
        quantity: int,
        order_type: str = "MKT",
        limit_price: float | None = None,
    ) -> str:
        """
        提交订单 → 返回 order_id (或拒绝原因)

        Args:
            symbol:      品种代码
            direction:   'LONG' 买入 / 'EXIT' 卖出
            quantity:    数量
            order_type:  'MKT' 市价 / 'LMT' 限价
            limit_price: 限价单价格 (仅 LMT 有效)

        Returns:
            order_id 字符串
        """
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict:
        """
        查询订单状态

        Returns:
            {
                'order_id': str,
                'status': 'pending' | 'partial' | 'filled' | 'cancelled' | 'rejected',
                'filled_qty': int,
                'avg_price': float,
                'commission': float,
                'created_at': datetime,
                'updated_at': datetime,
            }
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤单 → 返回是否成功"""
        ...

    @abstractmethod
    def get_positions(self) -> dict[str, dict]:
        """
        当前持仓

        Returns:
            {symbol: {'quantity': int, 'avg_cost': float, 'market_value': float}}
        """
        ...

    @abstractmethod
    def get_balance(self) -> dict:
        """
        账户余额

        Returns:
            {'cash': float, 'total_value': float, 'margin_used': float}
        """
        ...
