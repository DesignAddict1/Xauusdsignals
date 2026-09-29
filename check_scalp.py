#!/usr/bin/env python3
"""Dual-RSI scalping on XAU/USD. Entries come from the M15 chart
(RSI(14) for direction, RSI(5) for timing). Each alert also reports how
the M30 and H1 charts look, so you can see whether the bigger picture
agrees with the trade. One Telegram alert per setup, closed candles only."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.data import fetch_series
from signals.indicators import rsi, atr
from signals.rules import dual_rsi_signal, scalp_trade, RSI_FAST, RSI_SLOW
from signals.alerts import send_telegram
from signals.state import STATE_DIR

STATE_FILE = os.path.join(STATE_DIR, "scalp.json")
STALE_AFTER = timedelta(minutes=30)
HIGHER_TFS = [("M30", "30min", timedelta(minutes=30)), ("H1", "1h", timedelta(hours=1))]
M15 = timedelta(minutes=15)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def to_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def last_closed_index(times, bar: timedelta, at: datetime) -> int:
    """Index of the newest candle that had fully closed by time `at` (-1 if none)."""
    for k in range(len(times) - 1, -1, -1):
        if to_utc(times[k]) + bar <= at:
            return k
    return -1


def bias(r14) -> str:
    if r14 is None:
        return "no data"
    return "bullish" if r14 > 50 else "bearish" if r14 < 50 else "neutral"


def confidence(side: str, higher: list) -> tuple:
    """How many of M30/H1 point the same way as the trade (RSI(14) above/below 50)."""
    want = "bullish" if side == "BUY" else "bearish"
    agree = sum(1 for tf in higher if tf["bias"] == want)
    labels = {2: "Strong — M30 and H1 both agree",
              1: "Moderate — one higher timeframe agrees",
              0: "Weak — M30 and H1 both point the other way"}
    return agree, labels[agree]


def main():
    api_key = os.environ["TWELVE_DATA_KEY"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    data = fetch_series("XAU/USD", "15min", 300, api_key)
    closes, highs, lows, times = data["closes"], data["highs"], data["lows"], data["times"]

    print(f"[scalp] M15 candles after weekday filter: {len(closes)} (raw {data['raw_count']})")
    if len(closes) < 30:
        raise RuntimeError(f"Only {len(closes)} usable candles — need at least 30. meta: {data['meta']}")

    now = datetime.now(timezone.utc)
    i = last_closed_index(times, M15, now)
    bar_time = times[i]
    bar_close_time = to_utc(bar_time) + M15

    rsi_fast = rsi(closes, RSI_FAST)
    rsi_slow = rsi(closes, RSI_SLOW)
    atr14 = atr(highs, lows, closes, 14)

    sig = dual_rsi_signal(rsi_fast[i - 1], rsi_fast[i], rsi_slow[i])
    print(f"[scalp] M15 candle {bar_time} UTC close={closes[i]:.2f} "
          f"RSI(5) {rsi_fast[i - 1]:.1f}->{rsi_fast[i]:.1f} RSI(14)={rsi_slow[i]:.1f} -> {sig.label}")

    state = load_state()

    if sig.tone == "flat":
        print("[scalp] no setup, no alert")
    elif now - bar_close_time > STALE_AFTER:
        print(f"[scalp] setup is on an old candle ({bar_time}) — market closed or data delayed, not alerting")
    elif state.get("last_alert_bar") == bar_time:
        print("[scalp] already alerted for this candle")
    else:
        # Higher timeframes, read at the moment the M15 candle closed.
        higher = []
        for name, interval, bar in HIGHER_TFS:
            d = fetch_series("XAU/USD", interval, 300, api_key)
            k = last_closed_index(d["times"], bar, bar_close_time)
            r5, r14 = rsi(d["closes"], RSI_FAST), rsi(d["closes"], RSI_SLOW)
            if k < 0 or r14[k] is None:
                higher.append({"name": name, "r5": None, "r14": None, "bias": "no data"})
                print(f"[scalp] {name}: no closed candle with enough history")
                continue
            higher.append({"name": name, "r5": r5[k], "r14": r14[k], "bias": bias(r14[k])})
            print(f"[scalp] {name} candle {d['times'][k]} RSI(5)={r5[k]:.1f} RSI(14)={r14[k]:.1f} {bias(r14[k])}")

        trade = scalp_trade(sig.tone, closes[i], atr14[i])
        agree, conf_text = confidence(trade.action, higher)
        lagos_time = (bar_close_time + timedelta(hours=1)).strftime("%H:%M")
        lines = [
            f"*XAU/USD M15 — {trade.action} setup*",
            f"Candle closed {lagos_time} (Lagos) at `{closes[i]:.2f}`",
            "",
            f"*{trade.action}* near `{trade.entry:.2f}`",
            f"Stop-loss: `{trade.stop:.2f}`",
            f"Take-profit: `{trade.target:.2f}`",
            "",
            "*Timeframe report*",
            f"M15: RSI(5) `{rsi_fast[i - 1]:.1f}` -> `{rsi_fast[i]:.1f}`, RSI(14) `{rsi_slow[i]:.1f}` (entry trigger)",
        ]
        for tf in higher:
            if tf["r14"] is None:
                lines.append(f"{tf['name']}: no data")
            else:
                lines.append(f"{tf['name']}: RSI(5) `{tf['r5']:.1f}`, RSI(14) `{tf['r14']:.1f}` ({tf['bias']})")
        lines += [
            f"Confidence: *{conf_text}*",
            "",
            "Prices come from Twelve Data and can differ by a few points from your broker. "
            "Not financial advice.",
        ]
        send_telegram(bot_token, chat_id, "\n".join(lines))
        state["last_alert_bar"] = bar_time
        print(f"[scalp] alert sent ({agree}/2 higher timeframes agree)")

    state["last_checked_bar"] = bar_time
    state["tone"] = sig.tone
    save_state(state)


if __name__ == "__main__":
    main()
