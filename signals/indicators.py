"""EMA, RSI and ATR — direct ports of the same formulas used in the
browser dashboard, so backtest results and live alerts always agree
with what the dashboard shows."""

from typing import List, Optional


def ema(values: List[float], period: int) -> List[float]:
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values: List[float], period: int) -> List[Optional[float]]:
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d

    avg_g = gains / period
    avg_l = losses / period
    out: List[Optional[float]] = [None] * period
    out.append(100 - 100 / (1 + (100 if avg_l == 0 else avg_g / avg_l)))

    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        g = d if d > 0 else 0
        l = -d if d < 0 else 0
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        out.append(100 - 100 / (1 + (100 if avg_l == 0 else avg_g / avg_l)))
    return out


def atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[Optional[float]]:
    trs = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    out: List[Optional[float]] = [None] * len(trs)
    out[period - 1] = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    return out
