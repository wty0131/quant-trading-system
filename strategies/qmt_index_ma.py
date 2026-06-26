"""
QMT 指数成分股批量 MA 策略 — 从长城证券 QMT 适配

原QMT逻辑 (PY模型回测示例.py):
  init() → get_stock_list_in_sector('上证50') → 获取全部50只成分股
  handlebar() → 遍历 → MA5上穿MA20买入 → 死叉卖出 → 多symbol管理

适配: 继承 Strategy，在 on_bar() 中遍历所有注册的 symbol。
      受限于引擎当前单symbol回调，改为"虚拟遍历"——跟踪多只股票的状态。
"""

from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


def get_index_constituents(index: str = "上证50") -> list[str]:
    """
    获取指数成分股列表

    baostock 无直接获取成分股的接口，这里硬编码主要成分股。
    QMT原版用 ContextInfo.get_stock_list_in_sector()。
    """
    INDEX_STOCKS = {
        "上证50": [
            "sh.600519", "sh.600036", "sh.601318", "sh.600276",
            "sh.601012", "sz.000858", "sz.002415", "sh.600900",
            "sh.601398", "sh.601288", "sh.601857", "sh.600030",
            "sh.601166", "sh.600887", "sh.601668", "sh.601088",
            "sh.600050", "sh.601390", "sh.601688", "sh.600009",
            "sh.600585", "sh.601939", "sh.600104", "sh.601225",
            "sh.601328", "sh.600000", "sh.601601", "sh.600016",
            "sh.601989", "sh.601985", "sh.600031", "sh.601888",
            "sh.601628", "sh.600309", "sh.600837", "sh.601336",
            "sh.601818", "sh.600048", "sh.601066", "sh.601186",
        ],
    }
    return INDEX_STOCKS.get(index, [])


class QMTIndexMAStrategy(Strategy):
    """
    指数成分股批量MA策略 (QMT适配)

    用法:
      strategy = QMTIndexMAStrategy("上证50", short=5, long=20)
      engine = BacktestEngine(df_multi, strategy)

    每根bar检查当前symbol是否满足MA条件 → 信号。
    多股票切换由引擎的 _run_multi() 模式处理。
    """

    def __init__(
        self,
        index_name: str = "上证50",
        short: int = 5,
        long: int = 20,
    ):
        super().__init__()
        self.index_name = index_name
        self.short = short
        self.long = long
        self._positions: dict[str, bool] = {}  # {symbol: is_holding}
        self._constituents = get_index_constituents(index_name)
        print(f"[QMTIndexMA] {index_name} 成分股: {len(self._constituents)} 只")

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)

        ma_short = self.sma(bar.symbol, self.short)
        ma_long = self.sma(bar.symbol, self.long)
        if ma_short is None or ma_long is None:
            return None

        holding = self._positions.get(bar.symbol, False)

        if ma_short > ma_long and not holding:
            self._positions[bar.symbol] = True
            return self._bid(bar)
        elif ma_short < ma_long and holding:
            self._positions[bar.symbol] = False
            return self._ask(bar)

        return None
