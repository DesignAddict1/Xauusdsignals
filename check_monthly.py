#!/usr/bin/env python3
"""Runs once a day via GitHub Actions. Checks the daily/monthly trend
signal and pings Telegram whenever the bias flips (bullish/bearish/neutral)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.data import fetch_series
from signals.indicators import ema, rsi, atr
from signals.rules import trend_signal, trade_call
from signals.alerts import send_telegram
from signals.state import load_last_tone, save_last_tone

STATE_NAME = "monthly"


def main():
    api_key = os.environ["TWELVE_DATA_KEY"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    data = fetch_series("XAU/USD", "1day", 260, api_key)
    closes, highs, lows = data["closes"], data["highs"], data["lows"]

    ema50, ema200 = ema(closes, 50), ema(closes, 200)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)

    price = closes[-1]
    five_day_chg = closes[-1] - closes[-6]
    five_day_pct = five_day_chg / closes[-6] * 100

    sig = trend_signal(ema50[-1], ema200[-1], rsi14[-1])
    call = trade_call(sig.tone, price, atr14[-1], stop_mult=1.5, target_mult=3.0)

    print(f"[monthly] price={price:.2f} tone={sig.tone} label={sig.label} why={sig.why}")

    last_tone = load_last_tone(STATE_NAME)
    if sig.tone != last_tone:  # alert on every flip, including into "flat"/neutral
        lines = [
            f"*XAU/USD Monthly Trend — {sig.label}*",
            f"Price: `{price:.2f}`",
            sig.why,
            f"5-business-day change: `{five_day_chg:+.2f}` ({five_day_pct:+.2f}%)",
        ]
        if call.action != "NONE":
            lines += [
                "",
                f"*{call.action} {call.entry_low:.2f} – {call.entry_high:.2f}*",
                f"Stop: `{call.stop:.2f}`   Target: `{call.target:.2f}`",
                "_ATR-based levels, ~1:2 risk-reward. Not financial advice — confirm before entering._",
            ]
        send_telegram(bot_token, chat_id, "\n".join(lines))
        print("[monthly] alert sent")
    else:
        print("[monthly] no flip, no alert")

    save_last_tone(STATE_NAME, sig.tone)


if __name__ == "__main__":
    main()
