"""
自定义策略模板 — 复制此文件改名即可创建新策略

用法:
  1. 复制本文件: cp _template.py my_strategy.py
  2. 修改类名、name、category、description
  3. 实现 on_bar() 方法
  4. 重启仪表盘 → 新策略自动出现在回测页下拉菜单中

on_bar() 可用的基类方法:
  self.sma(symbol, period)      简单移动平均
  self.ema(symbol, period)      指数移动平均
  self.highest(symbol, period)  N日最高价
  self.lowest(symbol, period)   N日最低价
  self.atr(symbol, period)      平均真实波幅
  self.dastd(symbol, period)    半衰期加权标准差(QMT)
  self.hsigma(symbol, idx_sym, period)  加权Beta(QMT)
  self.cmra(symbol)            12月收益范围(QMT)
  self._bid(bar)                生成买入信号 (LONG)
  self._ask(bar)                生成卖出信号 (EXIT)
"""

from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class MyTemplateStrategy(Strategy):
    """
    在此处写策略的详细原理说明。
    引擎每根K线调用一次 on_bar()。
    返回 SignalEvent 表示交易信号，返回 None 表示不动。
    """

    # ── 必填：策略元信息（仪表盘自动读取）──
    name = "模板策略"
    category = "用户自定义"
    description = "复制 _template.py 即可创建自己的策略"

    def __init__(self, param1: int = 20, param2: float = 2.0):
        """
        构造参数会自动作为仪表盘滑块显示。
        int 参数 → 整数滑块
        float 参数 → 浮点滑块
        str 参数 → 文本输入
        """
        super().__init__()
        self.param1 = param1
        self.param2 = param2
        self._in_position = False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        # 更新价格历史（必须调用）
        self._update_price(bar.symbol, bar)

        # ===== 在这里写你的策略逻辑 =====
        ma = self.sma(bar.symbol, self.param1)
        if ma is None:
            return None

        # 示例: 收盘价 > MA 买入, < MA 卖出
        if bar.close > ma and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif bar.close < ma and self._in_position:
            self._in_position = False
            return self._ask(bar)

        return None
