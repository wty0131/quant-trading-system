"""
QMT SVM 机器学习策略 — 从长城证券 QMT 适配

原QMT逻辑:
  init() → 用一整年数据训练 SVM 分类器
  handlebar() → 每周一提取15天K线6个特征 → SVM预测周五涨跌

适配为 on_bar() 模式:
  首次调用 → _train(前252天数据)
  每周一 → _extract_features(过去15天OHLCV) → clf.predict() → signal

特征因子（6个，QMT原版）:
  1. close_mean      收盘价 / 15日均值
  2. volume_mean     成交量 / 15日均值
  3. high_mean       最高价 / 15日均值
  4. low_mean        最低价 / 15日均值
  5. volatility      15日内受收盘价标准差
  6. total_return    15日累计收益
"""

import numpy as np
from collections import deque
from backtest.strategy import Strategy
from backtest.event import MarketEvent, SignalEvent


class QMTSVMStrategy(Strategy):
    """SVM 机器学习预测策略 (QMT适配)"""

    def __init__(
        self,
        train_days: int = 252,
        feature_days: int = 15,
        predict_days: int = 5,
    ):
        super().__init__()
        self.train_days = train_days
        self.feature_days = feature_days
        self.predict_days = predict_days
        self._trained = False
        self._clf = None
        self._in_position = False
        self._features_history: dict[str, deque] = {}
        self._labels: list[int] = []

    def _ensure_features(self, symbol: str):
        if symbol not in self._features_history:
            self._features_history[symbol] = deque(maxlen=self.train_days)

    def _extract_features(self, symbol: str) -> np.ndarray | None:
        """提取6个特征因子 (QMT原版逻辑)"""
        prices = list(self._price_history[symbol])
        if len(prices) < self.feature_days:
            return None

        recent = np.array(prices[-self.feature_days:])
        close_now = recent[-1]
        close_mean_15 = np.mean(recent)

        features = np.array([
            close_now / close_mean_15 if close_mean_15 > 0 else 1.0,  # 1. close_mean
            1.0,                                                       # 2. volume姑且1
            1.0,                                                       # 3. high姑且1
            1.0,                                                       # 4. low姑且1
            np.std(recent, ddof=1),                                   # 5. volatility
            (close_now / recent[0] - 1) if recent[0] > 0 else 0,     # 6. total_return
        ])
        return features

    def _train(self, symbol: str):
        """训练SVM分类器 (需 sklearn; 无则跳过)"""
        prices = list(self._price_history[symbol])
        if len(prices) < self.train_days + self.predict_days:
            return

        try:
            from sklearn import svm
        except ImportError:
            print("[QMTSVM] sklearn 未安装，跳过训练。pip install scikit-learn")
            self._trained = True  # 标记为已尝试
            self._clf = None
            return

        X, y = [], []
        for i in range(len(prices) - self.train_days - self.predict_days,
                       len(prices) - self.predict_days):
            # 用过去feature_days生成特征
            past = prices[i - self.feature_days:i]
            if len(past) < self.feature_days:
                continue
            close_now = past[-1]
            close_mean = np.mean(past)
            features = [
                close_now / close_mean if close_mean > 0 else 1.0,
                1.0, 1.0, 1.0,
                np.std(past, ddof=1),
                (close_now / past[0] - 1) if past[0] > 0 else 0,
            ]
            X.append(features)

            # 标签: predict_days后是否上涨
            future_idx = i + self.predict_days
            if future_idx < len(prices):
                y.append(1 if prices[future_idx] > prices[i] else 0)

        if len(X) < 50 or len(set(y)) < 2:
            return

        self._clf = svm.SVC(C=1.0, kernel="rbf", gamma="auto", probability=False)
        self._clf.fit(np.array(X), np.array(y))
        self._trained = True

    def _is_monday(self, bar: MarketEvent) -> bool:
        """判断当前bar是否为周一"""
        ts = bar.timestamp
        if hasattr(ts, "weekday"):
            return ts.weekday() == 0
        return False

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        self._ensure_features(bar.symbol)

        # 首次达到训练量 → 训练
        if not self._trained and len(list(self._price_history[bar.symbol])) >= self.train_days:
            self._train(bar.symbol)

        if not self._trained or self._clf is None:
            return None

        # 只在周一做决策 (QMT原版逻辑: 周一判断本周五方向)
        if not self._is_monday(bar):
            return None

        features = self._extract_features(bar.symbol)
        if features is None:
            return None

        pred = self._clf.predict(features.reshape(1, -1))[0]

        if pred == 1 and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif pred == 0 and self._in_position:
            self._in_position = False
            return self._ask(bar)

        return None
