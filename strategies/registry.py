"""
策略注册中心 — 自动发现所有策略

用法:
  from strategies.registry import get_registry
  registry = get_registry()

  # 列出所有可用策略
  for name, cls, doc in registry.all():
      print(name, cls, doc)

  # 新增策略方法:
  # 1. 在 strategies/ 下创建 my_strategy.py
  # 2. 继承 backtest.strategy.Strategy, 实现 on_bar()
  # 3. 在类上添加 @register_strategy("策略名", category="分类", description="描述")
  # 4. 仪表盘和回测引擎自动发现

无装饰器方式（继承即自动注册）:
  class MyStrategy(Strategy):
      name = "我的策略"           # 显示名
      category = "用户自定义"      # 分类
      description = "策略描述"     # 说明
      def on_bar(self, bar): ...
"""
import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from typing import Type, Callable

from backtest.strategy import Strategy


@dataclass
class StrategyMeta:
    """策略元信息"""
    name: str
    cls: Type[Strategy]
    category: str = "未分类"
    description: str = ""
    params: dict = field(default_factory=dict)
    source_file: str = ""


class StrategyRegistry:
    """策略注册表 — 单例"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._strategies: dict[str, StrategyMeta] = {}
            cls._instance._discovered = False
        return cls._instance

    def discover(self) -> list[StrategyMeta]:
        """扫描 strategies/ 目录, 自动注册所有策略"""
        if self._discovered:
            return list(self._strategies.values())

        self._strategies = {}
        self._load_builtin()
        self._load_user_strategies()
        self._discovered = True
        return list(self._strategies.values())

    def _load_builtin(self):
        """加载内置策略"""
        from backtest.strategy import BuyAndHoldStrategy, DualMAStrategy
        from strategies.bollinger import BollingerStrategy
        from strategies.turtle import TurtleStrategy
        from strategies.rsrs import RSRSStrategy
        from strategies.multifactor import MultiFactorStrategy
        from strategies.pairs import PairsStrategy
        from strategies.qmt_svm import QMTSVMStrategy
        from strategies.qmt_arima import QMTARIMAStrategy
        from strategies.qmt_index_ma import QMTIndexMAStrategy

        builtins = [
            ("买入持有 (基准)", BuyAndHoldStrategy, "基准对照", "第一天全仓买入一直持有, 用于验证引擎正确性"),
            ("双均线", DualMAStrategy, "趋势跟踪", "MA5上穿MA20=金叉买入, 下穿=死叉卖出"),
            ("布林带", BollingerStrategy, "均值回归", "价格<下轨=买入, 价格>中轨=平仓, 赌统计回归"),
            ("海龟交易系统", TurtleStrategy, "趋势跟踪", "完整交易系统: 突破入场+ATR止损+金字塔加仓+均线出场"),
            ("RSRS 阻力支撑", RSRSStrategy, "量价结构", "最高价~最低价OLS回归斜率, 量化买方推力"),
            ("多因子选股", MultiFactorStrategy, "截面Alpha", "动量+反转+低波因子打分, 定期调仓选TopN"),
            ("配对交易", PairsStrategy, "统计套利", "两只高相关股票价差Z-Score偏离→套利回归"),
            ("QMT SVM 机器学习", QMTSVMStrategy, "机器学习", "15天K线6特征→SVM分类器预测涨跌"),
            ("QMT ARIMA 预测", QMTARIMAStrategy, "时间序列", "ARIMA模型预测短期走势, 无statsmodels则回退动量"),
            ("QMT 上证50 轮动", QMTIndexMAStrategy, "指数增强", "50只成分股MA交叉轮动, QMT原版策略适配"),
        ]
        for name, cls, cat, desc in builtins:
            self._register(name, cls, cat, desc)

    def _load_user_strategies(self):
        """扫描 strategies/ 目录查找用户自定义策略"""
        import strategies as pkg
        pkg_path = pkg.__path__

        for finder, mod_name, is_pkg in pkgutil.iter_modules(pkg_path):
            if mod_name.startswith('_') or mod_name.startswith('.'):
                continue

            # 跳过已注册的内置模块
            if mod_name in ('bollinger', 'turtle', 'rsrs', 'multifactor',
                           'pairs', 'qmt_svm', 'qmt_arima', 'qmt_index_ma'):
                continue

            try:
                mod = importlib.import_module(f'strategies.{mod_name}')
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (inspect.isclass(attr) and
                        issubclass(attr, Strategy) and
                        attr is not Strategy and
                        attr.__module__ == mod.__name__):

                        name = getattr(attr, 'name', mod_name.replace('_', ' ').title())
                        cat = getattr(attr, 'category', '用户自定义')
                        desc = getattr(attr, 'description', attr.__doc__ and attr.__doc__.strip().split('\n')[0] or '')

                        if name not in self._strategies:
                            params = {}
                            init_sig = inspect.signature(attr.__init__)
                            for p_name, p in init_sig.parameters.items():
                                if p_name not in ('self', 'args', 'kwargs') and p.default is not inspect.Parameter.empty:
                                    params[p_name] = p.default
                            self._register(name, attr, cat, desc, params, mod_name + '.py')
            except Exception:
                pass

    def _register(self, name, cls, category, description, params=None, source_file=''):
        self._strategies[name] = StrategyMeta(
            name=name,
            cls=cls,
            category=category,
            description=description,
            params=params or {},
            source_file=source_file,
        )

    def all(self) -> list[StrategyMeta]:
        """返回所有已注册策略"""
        if not self._discovered:
            self.discover()
        return list(self._strategies.values())

    def get(self, name: str) -> StrategyMeta | None:
        return self._strategies.get(name)

    def by_category(self) -> dict[str, list[StrategyMeta]]:
        """按分类分组"""
        groups = {}
        for meta in self.all():
            groups.setdefault(meta.category, []).append(meta)
        return groups


# 全局单例
def get_registry() -> StrategyRegistry:
    return StrategyRegistry()
