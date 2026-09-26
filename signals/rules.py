"""Signal rules — identical thresholds to the dashboard's JS, so the
alert you get on Telegram always matches what the dashboard would show
if you opened it at that moment."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    tone: str       # "up" | "down" | "flat"
    label: str
    why: str


def trend_signal(e50: float, e200: float, r14: float) -> Signal:
    if e50 > e200 and r14 > 50:
        return Signal("up", "Bullish", f"EMA50 above EMA200 and RSI(14) at {r14:.0f} — uptrend intact.")
    if e50 < e200 and r14 < 50:
        return Signal("down", "Bearish", f"EMA50 below EMA200 and RSI(14) at {r14:.0f} — downtrend intact.")
    return Signal("flat", "Neutral / mixed", f"EMA and RSI(14)={r14:.0f} disagree — trend is transitioning.")


def scalp_signal(e9: float, e21: float, r15: float) -> Signal:
    if e9 > e21 and 50 < r15 < 75:
        return Signal("up", "Buy bias", f"EMA9 above EMA21 on 15m, RSI(14)={r15:.0f} — momentum favors longs.")
    if e9 < e21 and 25 < r15 < 50:
        return Signal("down", "Sell bias", f"EMA9 below EMA21 on 15m, RSI(14)={r15:.0f} — momentum favors shorts.")
    if r15 >= 75:
        return Signal("down", "Overbought — caution", f"RSI(14)={r15:.0f} on 15m — stretched, pullback risk.")
    if r15 <= 25:
        return Signal("up", "Oversold — caution", f"RSI(14)={r15:.0f} on 15m — stretched, bounce risk.")
    return Signal("flat", "No clear edge", "EMA9/21 flat or crossing — wait for confirmation.")


@dataclass
class TradeCall:
    action: str          # "BUY" | "SELL" | "NONE"
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None


def trade_call(tone: str, price: float, atr_val: float,
                entry_mult: float = 0.5, stop_mult: float = 1.5, target_mult: float = 3.0) -> TradeCall:
    if tone == "flat" or atr_val is None:
        return TradeCall("NONE")

    is_buy = tone == "up"
    entry_far = price - entry_mult * atr_val if is_buy else price + entry_mult * atr_val
    entry_low, entry_high = sorted([price, entry_far])
    stop = (entry_low - stop_mult * atr_val) if is_buy else (entry_high + stop_mult * atr_val)
    target = (entry_high + target_mult * atr_val) if is_buy else (entry_low - target_mult * atr_val)

    return TradeCall("BUY" if is_buy else "SELL", entry_low, entry_high, stop, target)
