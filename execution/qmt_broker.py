"""
QMTBroker — A股实盘券商 (via xtquant/QMT)

适配券商: 长城证券 (Great Wall Securities) + 其他支持QMT的券商

开通步骤:
  1. 联系长城证券客户经理，申请 QMT 量化交易权限
     (资金门槛: 30~50万, 风险测评C4+, 1~3个工作日审核)
  2. 获取 QMT 安装包 + xtquant Python 库
  3. pip install xtquant (或券商提供的whl包)
  4. 在项目 .env 填入: QMT_ACCOUNT / QMT_PATH / QMT_MINI_MODE

连接方式:
  - miniQMT: 无需完整客户端，xtquant直连券商 (推荐)
  - 完整客户端: QMT客户端运行 → xtquant 连接本地端口

开通后只需修改 connect() 方法（框架已搭好），其余 Broker 接口自动适配。
"""

from datetime import datetime
from .broker import Broker


class QMTBroker(Broker):
    """A股实盘 (via xtquant/QMT)"""

    def __init__(
        self,
        account_id: str = "",
        qmt_path: str = "",
        mini_mode: bool = False,
    ):
        """
        Args:
            account_id: 资金账号
            qmt_path:   QMT 客户端安装路径
            mini_mode:  是否 miniQMT 模式
        """
        super().__init__()
        self.account_id = account_id
        self.qmt_path = qmt_path
        self.mini_mode = mini_mode
        self._xt_trader = None
        self._connected = False

        try:
            import xtquant.xttrader as xttrader
            self._has_xtquant = True
        except ImportError:
            self._has_xtquant = False
            print("[QMTBroker] xtquant 未安装。"
                  "请执行: pip install xtquant"
                  "或从券商处获取安装包")
        self._orders: dict[str, dict] = {}

    # ── 连接 (需用户根据券商配置填写) ──

    def connect(self) -> bool:
        """连接 QMT — 需根据券商的接入方式修改"""
        if not self._has_xtquant:
            return False
        try:
            # ==========================================
            # 用户根据券商提供的接入方式修改以下代码
            # ==========================================

            # 方式1: miniQMT (无需完整客户端)
            # from xtquant.xttrader import XtQuantClient
            # self._xt_trader = XtQuantClient()
            # self._xt_trader.login(self.account_id)

            # 方式2: 完整QMT客户端 (客户端需运行中)
            # from xtquant.xttrader import XtQuantTrader
            # self._xt_trader = XtQuantTrader(self.qmt_path)
            # self._xt_trader.start()
            # self._xt_trader.login(self.account_id)

            self._connected = True
            return True
        except Exception as e:
            print(f"[QMTBroker] 连接失败: {e}")
            return False

    # ── Broker 接口 ──

    def submit_order(self, symbol, direction, quantity, order_type="MKT", limit_price=None):
        if not self._connected:
            return "NOT_CONNECTED"
        return "QMT_PLACEHOLDER"  # 待用户实现

    def get_order_status(self, order_id: str) -> dict:
        return {"order_id": order_id, "status": "unknown"}

    def cancel_order(self, order_id: str) -> bool:
        return False

    def get_positions(self) -> dict[str, dict]:
        return {}

    def get_balance(self) -> dict:
        return {"cash": 0, "total_value": 0}
