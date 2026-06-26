"""
策略基类 — 所有策略的抽象接口

子类只需实现 on_bar() 方法，框架负责数据推送和信号处理。

用法:
    class MyStrategy(Strategy):
        def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
            # bar 是当前K线数据
            # 返回 SignalEvent 表示交易信号，返回 None 表示不动
            ...
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
import numpy as np

from .event import MarketEvent, SignalEvent, Direction


class Strategy(ABC):
    """
    策略抽象基类

    职责：
      - 接收 MarketEvent，分析后返回交易信号
      - 维护内部状态（指标值等）

    子类不可以访问未来数据（通过 deque 滚动窗口确保）
    """

    def __init__(self):
        self._price_history: dict[str, deque[float]] = {}

    @abstractmethod
    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        """
        每根K线回调 — 策略的核心逻辑

        Args:
            bar: 当前K线数据

        Returns:
            SignalEvent — 触发交易
            None       — 不操作
        """
        ...

    # ── 框架提供的便捷方法 ──

    def _ensure_history(self, symbol: str, max_period: int):
        """确保有足够长度的价格历史 deque"""
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=max_period)

    def _update_price(self, symbol: str, bar: MarketEvent):
        """更新价格历史"""
        self._ensure_history(symbol, 400)  # 预留 400 条（QMT指标需要252+）
        self._price_history[symbol].append(bar.close)

    def sma(self, symbol: str, period: int) -> float | None:
        """简单移动平均"""
        if symbol not in self._price_history:
            return None
        prices = list(self._price_history[symbol])
        if len(prices) < period:
            return None
        return float(np.mean(prices[-period:]))

    def ema(self, symbol: str, period: int) -> float | None:
        """指数移动平均（简化版）"""
        if symbol not in self._price_history:
            return None
        prices = np.array(self._price_history[symbol])
        if len(prices) < period:
            return None
        alpha = 2.0 / (period + 1)
        result = prices[0]
        for p in prices[1:]:
            result = alpha * p + (1 - alpha) * result
        return float(result)

    def highest(self, symbol: str, period: int) -> float | None:
        """N日最高价（收盘价）"""
        if symbol not in self._price_history:
            return None
        prices = list(self._price_history[symbol])
        if len(prices) < period:
            return None
        return float(np.max(prices[-period:]))

    def lowest(self, symbol: str, period: int) -> float | None:
        """N日最低价（收盘价）"""
        if symbol not in self._price_history:
            return None
        prices = list(self._price_history[symbol])
        if len(prices) < period:
            return None
        return float(np.min(prices[-period:]))

    def atr(self, symbol: str, period: int = 14) -> float | None:
        """平均真实波幅（简化，基于收盘价）"""
        if symbol not in self._price_history:
            return None
        prices = np.array(self._price_history[symbol])
        if len(prices) < period + 1:
            return None
        tr = np.abs(prices[1:] - prices[:-1])
        return float(np.mean(tr[-period:]))

    # ── QMT 内置指标（从长城证券 QMT 适配）──

    def dastd(self, symbol: str, period: int = 252) -> float | None:
        """
        DASTD: 半衰期加权标准差 (QMT原版)

        与普通 std 的区别：近期数据权重更高，半衰期=252天。
        第 i 天前的权重 = 0.5^(i/252)

        适用：波动率估算——昨天的波动比 250 天前的波动更重要
        """
        if symbol not in self._price_history:
            return None
        prices = list(self._price_history[symbol])
        if len(prices) < period + 1:
            return None
        rets = np.diff(prices[-(period+1):]) / prices[-(period+1):-1]
        n = len(rets)
        half_lift = pow(0.5, 1.0 / period)  # 半衰期因子
        weights = np.array([pow(half_lift, n - i) for i in range(n)])
        weights = weights / weights.sum()
        mean_r = np.average(rets, weights=weights)
        var = np.average((rets - mean_r) ** 2, weights=weights)
        return float(np.sqrt(var))

    def hsigma(
        self, symbol: str, index_symbol: str, period: int = 252
    ) -> float | None:
        """
        HSIGMA: 个股 vs 指数加权 Beta (QMT原版)

        对沪深300的OLS回归斜率，半衰期加权。
        Beta > 1 = 比大盘波动大，< 1 = 防御型。

        需要基类同时维护 index 的价格历史（通过 _update_price 两个symbol）。
        如果 index 不在 _price_history 中，回退到无加权 OLS。
        """
        if symbol not in self._price_history:
            return None
        stock_prices = list(self._price_history[symbol])
        if len(stock_prices) < period + 1:
            return None

        stock_rets = np.diff(stock_prices[-(period+1):]) / stock_prices[-(period+1):-1]
        n = len(stock_rets)

        # 尝试取指数收益率
        if index_symbol in self._price_history:
            idx_prices = list(self._price_history[index_symbol])
            idx_rets = np.diff(idx_prices[-(period+1):]) / idx_prices[-(period+1):-1]
            idx_rets = idx_rets[-n:]
        else:
            return None

        # 半衰期加权
        half_lift = pow(0.5, 1.0 / period)
        weights = np.array([pow(half_lift, n - i) for i in range(n)])
        w = weights / weights.sum()

        stock_mean = np.average(stock_rets, weights=w)
        idx_mean = np.average(idx_rets, weights=w)
        cov = np.average((stock_rets - stock_mean) * (idx_rets - idx_mean), weights=w)
        var = np.average((idx_rets - idx_mean) ** 2, weights=w)
        if var < 1e-12:
            return None
        return float(cov / var)

    def cmra(self, symbol: str) -> float | None:
        """
        CMRA: 12个月累计收益范围 (QMT原版)

        CMRA = ln((1+Zmax) / (1+Zmin))
        其中 Zt = 过去 t 个月的累计收益

        CMRA 越大 → 过去一年内股价波动范围越大
        用于衡量"极端收益离散度"
        """
        if symbol not in self._price_history:
            return None
        prices = list(self._price_history[symbol])
        if len(prices) < 12 * 21:  # 每月约21个交易日
            return None

        Z_list = []
        n = len(prices)
        for month in range(1, 13):
            start_idx = n - month * 21
            if start_idx < 0:
                continue
            close_start = prices[start_idx]
            close_end = prices[n - month * 21 + 20] if n - month * 21 + 20 < n else prices[-1]
            if close_start <= 0:
                continue
            Zt = (close_end - close_start) / close_start
            Z_list.append(Zt)

        if len(Z_list) < 2:
            return None
        Zmax, Zmin = max(Z_list), min(Z_list)
        if 1 + Zmin <= 0:
            return None
        return float(np.log((1 + Zmax) / (1 + Zmin)))

    def _bid(self, bar: MarketEvent) -> SignalEvent:
        """生成做多信号"""
        return SignalEvent(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            direction=Direction.LONG,
        )

    def _ask(self, bar: MarketEvent) -> SignalEvent:
        """生成平仓/做空信号"""
        return SignalEvent(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            direction=Direction.EXIT,
        )


class BuyAndHoldStrategy(Strategy):
    """
    买入持有策略 — 最简单的基准

    第一天全仓买入，最后一天卖出。
    用于验证回测引擎正确性。
    """

    def __init__(self):
        super().__init__()
        self._bought = False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        if not self._bought:
            self._bought = True
            return self._bid(bar)
        return None


class DualMAStrategy(Strategy):
    """双均线策略 — 金叉买入，死叉卖出"""

    def __init__(self, short: int = 5, long: int = 20):
        super().__init__()
        self.short = short
        self.long = long
        self._in_position = False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)

        ma_short = self.sma(bar.symbol, self.short)
        ma_long = self.sma(bar.symbol, self.long)

        # 需要足够数据
        if ma_short is None or ma_long is None:
            return None

        # 金叉：短线上穿长线，且当前未持仓
        if ma_short > ma_long and not self._in_position:
            self._in_position = True
            return self._bid(bar)

        # 死叉：短线下穿长线，且当前持仓
        if ma_short < ma_long and self._in_position:
            self._in_position = False
            return self._ask(bar)

        return None
