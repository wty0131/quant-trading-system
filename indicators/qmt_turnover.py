"""
QMT 流动性因子 — STOA / STOM / STOQ (从长城证券 QMT 适配)

原QMT指标:
  STOM = ln(Σ(vol_i / circulating_cap_i))  月度换手率
  STOA = ln(avg(exp(STOM_i)))              年度换手率
  STOQ = ln(avg(exp(STOM_i)))              季度换手率

注意:
  - baostock 无流通股本数据 → 用 volume/100 近似（标准化即可）
  - 这些因子用于多因子策略中的"流动性"维度
  - 换手率越高 → 股票越活跃 → 流动性溢价/折价
"""

import numpy as np
import pandas as pd


def stom(
    df: pd.DataFrame,
    period: int = 21,
    cap_approx: float = 1e8,
) -> pd.Series:
    """
    月度换手率 (Share Turnover per Month)

    STOM = ln(Σ(volume_i / circulating_cap_i) for i in 1..period)

    Args:
        df:         OHLCV DataFrame (需含 volume, symbol, date)
        period:     计算周期（默认21天≈1个月）
        cap_approx: 流通股本近似值。baostock无此数据，用固定值使指标可比较

    Returns:
        STOM 序列（前period-1个值为NaN）
    """
    result = pd.Series(index=df.index, dtype=float)
    for i in range(period - 1, len(df)):
        vol_slice = df.iloc[i - period + 1 : i + 1]["volume"]
        total = (vol_slice / cap_approx).sum()
        if total > 0:
            result.iloc[i] = float(np.log(total))
    return result


def stoa(
    df: pd.DataFrame,
    period: int = 252,
    cap_approx: float = 1e8,
) -> pd.Series:
    """
    年度换手率 (Share Turnover per Annum)

    STOA = ln(avg(exp(STOM_i) for i in 1..12))

    每月21天 → 12个月 = 252天
    """
    result = pd.Series(index=df.index, dtype=float)
    for i in range(period - 1, len(df)):
        stom_sum = 0.0
        for month_i in range(12):
            start = i - (month_i + 1) * 21
            end = i - month_i * 21
            if start < 0:
                continue
            vol_slice = df.iloc[start:end]["volume"]
            total = (vol_slice / cap_approx).sum()
            if total > 0:
                stom_sum += np.exp(np.log(total))
        if stom_sum > 0:
            result.iloc[i] = float(np.log(stom_sum / 12))
    return result


def stoq(
    df: pd.DataFrame,
    period: int = 63,
    cap_approx: float = 1e8,
) -> pd.Series:
    """
    季度换手率 (Share Turnover per Quarter)

    STOQ = ln(avg(exp(STOM_i) for i in 1..3))

    每月21天 → 3个月 = 63天
    """
    result = pd.Series(index=df.index, dtype=float)
    for i in range(period - 1, len(df)):
        stom_sum = 0.0
        for month_i in range(3):
            start = i - (month_i + 1) * 21
            end = i - month_i * 21
            if start < 0:
                continue
            vol_slice = df.iloc[start:end]["volume"]
            total = (vol_slice / cap_approx).sum()
            if total > 0:
                stom_sum += np.exp(np.log(total))
        if stom_sum > 0:
            result.iloc[i] = float(np.log(stom_sum / 3))
    return result
