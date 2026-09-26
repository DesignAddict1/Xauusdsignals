"""Synthetic smoke test — no network calls. Confirms indicators, rules,
trade_call and the state store all run cleanly end to end before this
ships to a live schedule."""

import math
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signals.indicators import ema, rsi, atr
from signals.rules import trend_signal, scalp_signal, trade_call
from signals.state import load_last_tone, save_last_tone, STATE_DIR

random.seed(42)


def fake_series(n, start=2650.0, vol=4.0):
    closes, highs, lows = [], [], []
    price = start
    for i in range(n):
        drift = 0.15 * math.sin(i / 20)
        price += random.gauss(drift, vol * 0.15)
        high = price + abs(random.gauss(0, vol * 0.3))
        low = price - abs(random.gauss(0, vol * 0.3))
        closes.append(price)
        highs.append(high)
        lows.append(low)
    return highs, lows, closes


def main():
    # --- daily / monthly path ---
    highs, lows, closes = fake_series(300)
    e50, e200 = ema(closes, 50), ema(closes, 200)
    r14 = rsi(closes, 14)
    a14 = atr(highs, lows, closes, 14)
    assert len(e50) == len(closes) and len(e200) == len(closes)
    assert r14[13] is None and r14[14] is not None
    assert a14[12] is None and a14[13] is not None

    sig = trend_signal(e50[-1], e200[-1], r14[-1])
    assert sig.tone in ("up", "down", "flat")
    call = trade_call(sig.tone, closes[-1], a14[-1])
    print(f"[monthly test] price={closes[-1]:.2f} tone={sig.tone} label={sig.label}")
    if call.action != "NONE":
        assert call.stop is not None and call.target is not None
        print(f"  -> {call.action} {call.entry_low:.2f}-{call.entry_high:.2f} stop={call.stop:.2f} target={call.target:.2f}")

    # --- 15m / scalp path ---
    highs2, lows2, closes2 = fake_series(150, vol=2.0)
    e9, e21 = ema(closes2, 9), ema(closes2, 21)
    r14b = rsi(closes2, 14)
    a14b = atr(highs2, lows2, closes2, 14)
    sig2 = scalp_signal(e9[-1], e21[-1], r14b[-1])
    call2 = trade_call(sig2.tone, closes2[-1], a14b[-1])
    print(f"[scalp test] price={closes2[-1]:.2f} tone={sig2.tone} label={sig2.label}")
    if call2.action != "NONE":
        print(f"  -> {call2.action} {call2.entry_low:.2f}-{call2.entry_high:.2f} stop={call2.stop:.2f} target={call2.target:.2f}")

    # --- state store round-trip ---
    test_name = "smoke_test"
    assert load_last_tone(test_name) is None
    save_last_tone(test_name, "up")
    assert load_last_tone(test_name) == "up"
    save_last_tone(test_name, "down")
    assert load_last_tone(test_name) == "down"
    os.remove(os.path.join(STATE_DIR, f"{test_name}.json"))

    # exercise every branch of both rule functions directly
    assert trend_signal(105, 100, 60).tone == "up"
    assert trend_signal(95, 100, 40).tone == "down"
    assert trend_signal(100, 100, 50).tone == "flat"
    assert scalp_signal(21, 20, 60).tone == "up"
    assert scalp_signal(19, 20, 40).tone == "down"
    assert scalp_signal(19, 20, 80).tone == "down"
    assert scalp_signal(21, 20, 10).tone == "up"
    assert scalp_signal(20, 20, 50).tone == "flat"
    assert trade_call("flat", 100, 1).action == "NONE"
    buy = trade_call("up", 2650, 3)
    assert buy.action == "BUY" and buy.stop < buy.entry_low < buy.entry_high < buy.target
    sell = trade_call("down", 2650, 3)
    assert sell.action == "SELL" and sell.target < sell.entry_low < sell.entry_high < sell.stop

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
