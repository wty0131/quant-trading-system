"""
QMT ARIMA 预测策略 — 从长城证券 QMT 适配

原QMT逻辑:
  handlebar() → 取240日收盘价 → 3阶差分 → ARIMA(4,3)拟合 → predict未来5天
  → 原版只画图(paint)不做交易

适配后: 滚动ARIMA(4,3) → 方向预测 → 信号

注意: ARIMA 每根 bar 都要重新拟合，计算量大。
      实际使用中降低 refit_freq（如每5天重训练一次）。
"""

import numpy as np
from collections import deque
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent
import warnings


class QMTARIMAStrategy(Strategy):
    """ARIMA 时间序列预测策略 (QMT适配)"""

    def __init__(
        self,
        history: int = 120,              # 历史窗口（降默认值适配短区间回测）
        order: tuple = (2, 1, 2),       # 简化ARIMA阶数减少收敛问题
        refit_freq: int = 5,            # 每 N 根 bar 重训练一次
    ):
        super().__init__()
        self.history = history
        self.order = order
        self.refit_freq = refit_freq
        self._in_position = False
        self._bars_since_refit = 0
        self._last_prediction: dict[str, int] = {}  # 0=跌, 1=涨

    def _arima_predict(self, symbol: str) -> int | None:
        """ARIMA拟合 → 预测下一日方向 (需statsmodels; 无则用简单动量)"""
        prices = np.array(list(self._price_history[symbol]))
        if len(prices) < self.history:
            return None

        recent = prices[-self.history:]
        try:
            from statsmodels.tsa.arima.model import ARIMA
            log_prices = np.log(recent)
            diff = np.diff(log_prices)
            model = ARIMA(diff, order=self.order)
            result = model.fit()
            forecast = result.forecast(steps=1)[0]
            return 1 if forecast > 0 else 0
        except ImportError:
            # 回退: 简单动量——昨天涨=预测涨
            return 1 if recent[-1] > recent[-2] else 0
        except Exception:
            return None

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        self._bars_since_refit += 1

        if self._bars_since_refit < self.refit_freq:
            # 使用上一轮预测结果
            pred = self._last_prediction.get(bar.symbol)
            if pred is not None:
                if pred == 1 and not self._in_position:
                    self._in_position = True
                    return self._bid(bar)
                elif pred == 0 and self._in_position:
                    self._in_position = False
                    return self._ask(bar)
            return None

        # 重训练
        self._bars_since_refit = 0
        pred = self._arima_predict(bar.symbol)
        if pred is not None:
            self._last_prediction[bar.symbol] = pred

        if pred == 1 and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif pred == 0 and self._in_position:
            self._in_position = False
            return self._ask(bar)

        return None
