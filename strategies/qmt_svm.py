"""
QMT SVM 机器学习策略 — 从长城证券 QMT 适配

原QMT逻辑:
  init() → 用一整年数据训练 SVM 分类器
  handlebar() → 每周一提取15天K线6个特征 → SVM预测周五涨跌

适配为 on_bar() 模式:
  积累足够数据 → 用历史窗口训练SVM → 每bar预测 → 信号

特征因子（6个，QMT原版）:
  1. close_mean      收盘价 / 15日均值
  2. volume_mean     成交量 / 15日均值  (用价格替代，baostock无实时volume特征)
  3. high_mean       最高价 / 15日均值  (同上)
  4. low_mean        最低价 / 15日均值  (同上)
  5. volatility      15日收盘价标准差
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
        train_days: int = 120,        # 训练数据量（降低默认值以适应短区间回测）
        feature_days: int = 15,       # 特征窗口
        predict_days: int = 5,        # 预测未来几天
        retrain_freq: int = 20,       # 每N根bar重新训练一次
        min_train_samples: int = 30,  # 最小训练样本数
    ):
        super().__init__()
        self.train_days = train_days
        self.feature_days = feature_days
        self.predict_days = predict_days
        self.retrain_freq = retrain_freq
        self.min_train_samples = min_train_samples
        self._trained = False
        self._clf = None
        self._in_position = False
        self._bars_since_retrain = 0

    def _extract_features(self, symbol: str) -> np.ndarray | None:
        """提取6个特征因子"""
        prices = list(self._price_history[symbol])
        if len(prices) < self.feature_days:
            return None

        recent = np.array(prices[-self.feature_days:])
        close_now = recent[-1]
        close_mean_15 = np.mean(recent)
        if close_mean_15 <= 0:
            return None

        return np.array([
            close_now / close_mean_15,                                 # 1. 价格/均价
            (recent[-1] - recent[-2]) / abs(recent[-2]) if recent[-2] != 0 else 0,  # 2. 日内动量
            (np.max(recent) - np.min(recent)) / close_mean_15,        # 3. 区间振幅
            (close_now - np.min(recent)) / (np.max(recent) - np.min(recent) + 1e-9),  # 4. 相对位置
            np.std(recent, ddof=1) / close_mean_15,                   # 5. 标准化波动率
            (close_now / recent[0] - 1) if recent[0] > 0 else 0,     # 6. 累计收益
        ])

    def _train(self, symbol: str):
        """
        训练SVM分类器

        用前面的数据训练，用最后一段做"验证集"的标签。
        训练集与预测时间窗口严格分离（避免数据泄漏）。
        """
        prices = list(self._price_history[symbol])
        total_needed = self.train_days + self.feature_days + self.predict_days
        if len(prices) < total_needed:
            return

        try:
            from sklearn import svm
        except ImportError:
            self._trained = True
            self._clf = None
            return

        X, y = [], []

        # 训练数据: 用前 train_days 根 bar 生成样本
        # 每条样本用 t-feature_days:t 的特征，标签是 t+predict_days 的涨跌
        train_start = len(prices) - self.train_days - self.predict_days
        train_end = len(prices) - self.predict_days

        for i in range(train_start, train_end):
            if i < self.feature_days:
                continue
            past = prices[i - self.feature_days : i]
            close_now = prices[i]
            close_mean = np.mean(past)
            if close_mean <= 0:
                continue

            features = [
                close_now / close_mean,
                (past[-1] - past[-2]) / abs(past[-2]) if past[-2] != 0 else 0,
                (np.max(past) - np.min(past)) / close_mean,
                (close_now - np.min(past)) / (np.max(past) - np.min(past) + 1e-9),
                np.std(past, ddof=1) / close_mean,
                (close_now / past[0] - 1) if past[0] > 0 else 0,
            ]
            X.append(features)

            future_idx = i + self.predict_days
            y.append(1 if future_idx < len(prices) and prices[future_idx] > close_now else 0)

        if len(X) < self.min_train_samples or len(set(y)) < 2:
            return

        self._clf = svm.SVC(C=1.0, kernel="rbf", gamma="scale", probability=False)
        self._clf.fit(np.array(X), np.array(y))
        self._trained = True

    def on_bar(self, bar: MarketEvent) -> SignalEvent | None:
        self._update_price(bar.symbol, bar)
        self._bars_since_retrain += 1

        # 首次训练 + 定期重训练
        need_retrain = (
            not self._trained
            or (self._trained and self._bars_since_retrain >= self.retrain_freq)
        )

        if need_retrain:
            self._train(bar.symbol)
            self._bars_since_retrain = 0

        if not self._trained or self._clf is None:
            return None

        # 提取当前特征 → 预测
        features = self._extract_features(bar.symbol)
        if features is None:
            return None

        try:
            pred = self._clf.predict(features.reshape(1, -1))[0]
        except Exception:
            return None

        if pred == 1 and not self._in_position:
            self._in_position = True
            return self._bid(bar)
        elif pred == 0 and self._in_position:
            self._in_position = False
            return self._ask(bar)

        return None
