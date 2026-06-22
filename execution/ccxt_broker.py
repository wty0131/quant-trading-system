"""
CCXTBroker — 加密交易所实盘/测试网

通过 ccxt 连接真实交易所:
  - 现货交易 (spot)
  - 支持市价单和限价单
  - 走 SOCKS5 代理 (国内网络需要)

安全提醒:
  - 默认用测试网 (testnet)，不影响真实资金
  - 实盘需显式设置 testnet=False
"""

from datetime import datetime
import os
from .broker import Broker
from .oms import OrderStatus


class CCXTBroker(Broker):
    """加密货币实盘券商 (via ccxt)"""

    def __init__(
        self,
        exchange_name: str = "gate",
        testnet: bool = True,
        api_key: str = "",
        secret: str = "",
        proxy: str | None = None,
    ):
        """
        Args:
            exchange_name: 交易所 ('gate', 'binance', 'okx'...)
            testnet:       是否用测试网
            api_key:       API Key (可选，公开行情不需要)
            secret:        Secret Key
            proxy:         SOCKS5 代理
        """
        super().__init__()
        self.exchange_name = exchange_name
        self.testnet = testnet
        self._proxy = proxy or os.environ.get("PROXY_SOCKS5")

        import ccxt
        config = {
            "enableRateLimit": True,
            "timeout": 30000,
        }
        if api_key and secret:
            config["apiKey"] = api_key
            config["secret"] = secret
        if self._proxy:
            config["proxies"] = {"http": self._proxy, "https": self._proxy}

        cls = getattr(ccxt, exchange_name)
        self._exchange = cls(config)
        if testnet:
            self._exchange.set_sandbox_mode(True)

        self._orders: dict[str, dict] = {}

    # ── Broker 接口 ──

    def submit_order(self, symbol, direction, quantity, order_type="MKT", limit_price=None):
        try:
            side = "buy" if direction == "LONG" else "sell"
            if order_type == "LMT" and limit_price:
                result = self._exchange.create_limit_order(symbol, side, quantity, limit_price)
            else:
                result = self._exchange.create_market_order(symbol, side, quantity)

            oid = result.get("id", str(datetime.now().timestamp()))
            self._orders[oid] = {
                "order_id": oid,
                "symbol": symbol,
                "status": result.get("status", "open"),
                "filled_qty": float(result.get("filled", 0)),
                "avg_price": float(result.get("price") or 0),
                "created_at": datetime.now(),
            }
            return str(oid)

        except Exception as e:
            # 测试网不可用时 fallback 到纸交易
            oid = f"ccxt_err_{datetime.now().timestamp()}"
            self._orders[oid] = {
                "order_id": oid, "symbol": symbol,
                "status": "rejected", "error": str(e),
                "created_at": datetime.now(),
            }
            return oid

    def get_order_status(self, order_id: str) -> dict:
        if order_id in self._orders:
            return self._orders[order_id]
        try:
            result = self._exchange.fetch_order(order_id)
            return {"order_id": order_id, "status": result.get("status", "unknown"),
                    "filled_qty": float(result.get("filled", 0)),
                    "avg_price": float(result.get("price") or 0)}
        except Exception:
            return {"order_id": order_id, "status": "unknown"}

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._exchange.cancel_order(order_id)
            if order_id in self._orders:
                self._orders[order_id]["status"] = "cancelled"
            return True
        except Exception:
            return False

    def get_positions(self) -> dict[str, dict]:
        try:
            balance = self._exchange.fetch_balance()
            positions = {}
            for sym, data in balance.get("total", {}).items():
                if data and data > 0:
                    positions[sym] = {"quantity": float(data), "avg_cost": 0.0}
            return positions
        except Exception:
            return {}

    def get_balance(self) -> dict:
        try:
            bal = self._exchange.fetch_balance()
            return {
                "cash": float(bal.get("USDT", {}).get("free", 0)),
                "total_value": float(bal.get("total", {}).get("USDT", 0)),
            }
        except Exception:
            return {"cash": 0, "total_value": 0}
