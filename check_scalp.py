#!/usr/bin/env python3
"""Runs every 15 minutes via GitHub Actions. Checks the 15-min scalping
signal and pings Telegram only when the bias flips to something new."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.data import fetch_series
from signals.indicators import ema, rsi, atr
from signals.rules import scalp_signal, trade_call
from signals.alerts import send_telegram
from signals.state import load_last_tone, save_last_tone

STATE_NAME = "scalp"


def main():
    api_key = os.environ["TWELVE_DATA_KEY"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    data = fetch_series("XAU/USD", "15min", 300, api_key)
    closes, highs, lows = data["closes"], data["highs"], data["lows"]

    print(f"[scalp] raw candles from API: {data['raw_count']}, after weekday filter: {len(closes)}")
    print(f"[scalp] meta: {data['meta']}")
    if data["times"]:
        print(f"[scalp] range: {data['times'][0]} to {data['times'][-1]}")
    if len(closes) < 22:
        raise RuntimeError(
            f"Only {len(closes)} usable candles — need at least 22 for EMA21/RSI14. "
            "This usually means the API plan doesn't support this interval/outputsize, "
            "or returned fewer rows than requested. See the [scalp] meta line above."
        )

    ema9, ema21 = ema(closes, 9), ema(closes, 21)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)

    price = closes[-1]
    sig = scalp_signal(ema9[-1], ema21[-1], rsi14[-1])
    call = trade_call(sig.tone, price, atr14[-1])

    print(f"[scalp] price={price:.2f} tone={sig.tone} label={sig.label} why={sig.why}")

    last_tone = load_last_tone(STATE_NAME)
    if sig.tone != "flat" and sig.tone != last_tone:
        lines = [
            f"*XAU/USD Scalp Signal — {sig.label}*",
            f"Price: `{price:.2f}`",
            sig.why,
        ]
        if call.action != "NONE":
            lines += [
                "",
                f"*{call.action} {call.entry_low:.2f} – {call.entry_high:.2f}*",
                f"Stop: `{call.stop:.2f}`   Target: `{call.target:.2f}`",
                "_ATR-based levels, ~1:2 risk-reward. Not financial advice — confirm before entering._",
            ]
        send_telegram(bot_token, chat_id, "\n".join(lines))
        print("[scalp] alert sent")
    else:
        print("[scalp] no flip, no alert")

    save_last_tone(STATE_NAME, sig.tone)


if __name__ == "__main__":
    main()
