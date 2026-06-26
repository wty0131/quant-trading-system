"""
QMTBroker — A股实盘 via xtquant/QMT (长城证券)

已安装: xtquant-250516.1.1 (2025年5月版)

使用前:
  1. 双击启动 QMT miniQMT: 长城测试交易系统/bin.x64/XtMiniQmt.exe
  2. 在迷你QMT中登录你的长城证券账户
  3. QMT_PATH 指向 QMT 安装根目录
  4. 确认 xtquant 已安装: pip install xtquant
"""

import os
import time
from datetime import datetime

from .broker import Broker


class QMTBroker(Broker):
    """A股实盘 — xtquant/QMT (长城证券)"""

    def __init__(
        self,
        account_id: str = "",
        qmt_path: str = "",
        session_id: int = 123456,
    ):
        super().__init__()
        self.account_id = account_id or os.environ.get("QMT_ACCOUNT", "")
        self.qmt_path = qmt_path or os.environ.get(
            "QMT_PATH",
            r"C:\Users\wty0131\Downloads\长城测试交易系统",
        )
        self.session_id = session_id

        self._xt_trader = None
        self._account = None
        self._connected = False
        self._positions: dict[str, dict] = {}
        self._cash: float = 0
        self._total_value: float = 0

        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
            from xtquant import xtconstant
            self._has_xtquant = True
            self._xtconstant = xtconstant
            self._StockAccount = StockAccount
            self._XtQuantTrader = XtQuantTrader
        except ImportError:
            self._has_xtquant = False
            print("[QMTBroker] 请安装: pip install xtquant")

    # ==========================================
    #  连接
    # ==========================================
    def connect(self) -> bool:
        """连接 miniQMT (需 XtMiniQmt.exe 在运行)"""
        if not self._has_xtquant:
            print("[QMTBroker] xtquant 未安装")
            return False

        try:
            # 创建 xtquant trader 实例
            self._xt_trader = self._XtQuantTrader(
                self.qmt_path,              # QMT 安装根目录
                self.session_id,            # 会话ID (任意整数)
            )

            # 注册回调
            callback = _QMTTraderCallback(self)
            self._xt_trader.register_callback(callback)

            # 启动连接
            self._xt_trader.start()
            print(f"[QMTBroker] 已连接: {self.qmt_path}")

            # 连接成功后，创建账户对象并订阅
            time.sleep(0.5)
            self._account = self._StockAccount(self.account_id)
            self._xt_trader.subscribe(self._account)

            self._connected = True
            print(f"[QMTBroker] 已订阅账户: {self.account_id}")
            return True

        except Exception as e:
            print(f"[QMTBroker] 连接失败: {e}")
            print("  请确认: 1) XtMiniQmt.exe 正在运行")
            print("         2) QMT_PATH 指向正确路径")
            return False

    # ==========================================
    #  Broker 接口
    # ==========================================
    def submit_order(
        self, symbol, direction, quantity, order_type="MKT", limit_price=None
    ) -> str:
        """
        下单

        symbol 转换: sh.600519 → 600519.SH  (baostock → xtquant格式)
        """
        if not self._connected:
            return "NOT_CONNECTED"

        # 转换 symbol 格式
        code = self._to_xtquant_symbol(symbol)

        # 方向
        if direction == "LONG":
            bs = self._xtconstant.STOCK_BUY
            price_type = self._xtconstant.LATEST_PRICE  # 市价
        elif direction == "EXIT":
            bs = self._xtconstant.STOCK_SELL
            price_type = self._xtconstant.LATEST_PRICE
        else:
            return "INVALID_DIRECTION"

        try:
            result = self._xt_trader.order_stock(
                self.account_id,        # 资金账号
                code,                   # 600519.SH
                bs,                     # 买卖方向
                quantity,               # 数量
                price_type,             # 价格类型
                limit_price or 0,       # 限价（市价为0）
                "",                     # 策略名称
                "",                     # 备注
            )
            oid = str(result) if result else str(datetime.now().timestamp())
            print(f"[QMTBroker] 下单: {code} {direction} {quantity}股 → {oid}")
            return oid

        except Exception as e:
            print(f"[QMTBroker] 下单失败: {e}")
            return f"ERROR_{e}"

    def get_order_status(self, order_id: str) -> dict:
        """查询订单状态（由回调自动更新）"""
        # xtquant 回调会自动更新 _last_order_status
        if not self._connected:
            return {"order_id": order_id, "status": "NOT_CONNECTED"}
        try:
            orders = self._xt_trader.query_stock_orders(self.account_id)
            for o in (orders or []):
                if str(getattr(o, "m_nOrderId", "")) == order_id:
                    return {
                        "order_id": order_id,
                        "status": getattr(o, "m_nOrderState", "unknown"),
                        "filled_qty": int(getattr(o, "m_nVolumeTraded", 0)),
                        "avg_price": float(getattr(o, "m_dTradedPrice", 0)),
                    }
        except Exception as e:
            return {"order_id": order_id, "status": f"error: {e}"}
        return {"order_id": order_id, "status": "not_found"}

    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if not self._connected:
            return False
        try:
            self._xt_trader.cancel_order_stock(self.account_id, int(order_id))
            return True
        except Exception:
            return False

    def get_positions(self) -> dict[str, dict]:
        """当前持仓（由回调实时更新）"""
        if not self._connected or not self._xt_trader:
            return self._positions

        try:
            positions = self._xt_trader.query_stock_positions(self.account_id)
            result = {}
            for pos in (positions or []):
                code = getattr(pos, "m_strInstrumentID", "")
                result[code] = {
                    "quantity": int(getattr(pos, "m_nVolume", 0)),
                    "avg_cost": float(getattr(pos, "m_dOpenPrice", 0)),
                    "market_value": float(getattr(pos, "m_dMarketValue", 0)),
                }
            self._positions = result
            return result
        except Exception:
            return self._positions

    def get_balance(self) -> dict:
        """账户余额（由回调实时更新）"""
        if not self._connected or not self._xt_trader:
            return {"cash": self._cash, "total_value": self._total_value}

        try:
            assets = self._xt_trader.query_stock_asset(self.account_id)
            if assets:
                cash = float(getattr(assets, "m_dAvailable", 0))
                total = float(getattr(assets, "m_dBalance", cash))
                self._cash = cash
                self._total_value = total
        except Exception:
            pass
        return {"cash": self._cash, "total_value": self._total_value}

    # ==========================================
    #  工具方法
    # ==========================================
    @staticmethod
    def _to_xtquant_symbol(symbol: str) -> str:
        """
        baostock → xtquant 格式转换
          sh.600519 → 600519.SH
          sz.300750 → 300750.SZ
          sh.000300 → 000300.SH
        """
        parts = symbol.split(".")
        if len(parts) == 2:
            return f"{parts[1]}.{parts[0].upper()}"
        return symbol

    def disconnect(self):
        """断开连接"""
        if self._xt_trader:
            try:
                self._xt_trader.stop()
            except Exception:
                pass
        self._connected = False


class _QMTTraderCallback:
    """xtquant 交易回调 — 接收订单状态、成交回报、持仓变更"""

    def __init__(self, broker: QMTBroker):
        self._broker = broker

    def on_disconnected(self):
        print("[QMT] 连接断开")

    def on_stock_order(self, order):
        status_map = {
            0: "unknown", 48: "pending", 49: "pending",
            50: "filled", 51: "filled", 52: "filled",
            53: "filled", 54: "partial", 55: "cancelled",
            56: "cancelled", 57: "rejected",
        }
        state = int(getattr(order, "m_nOrderState", 0))
        status = status_map.get(state, f"state_{state}")
        print(f"[QMT] 订单更新: {order.m_strInstrumentID} "
              f"qty={order.m_nVolumeTraded}/{order.m_nVolumeTotal} "
              f"status={status}")

    def on_stock_asset(self, asset):
        self._broker._cash = float(getattr(asset, "m_dAvailable", 0))
        self._broker._total_value = float(getattr(asset, "m_dBalance", 0))

    def on_stock_position(self, position):
        code = getattr(position, "m_strInstrumentID", "")
        self._broker._positions[code] = {
            "quantity": int(getattr(position, "m_nVolume", 0)),
            "avg_cost": float(getattr(position, "m_dOpenPrice", 0)),
            "market_value": float(getattr(position, "m_dMarketValue", 0)),
        }
