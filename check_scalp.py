#!/usr/bin/env python3
"""Dual-RSI scalping on XAU/USD M15: RSI(14) gives the direction, RSI(5)
gives the entry. One Telegram alert per setup, on closed candles only."""

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
BAR = timedelta(minutes=15)
STALE_AFTER = timedelta(minutes=30)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    api_key = os.environ["TWELVE_DATA_KEY"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    data = fetch_series("XAU/USD", "15min", 300, api_key)
    closes, highs, lows, times = data["closes"], data["highs"], data["lows"], data["times"]

    print(f"[scalp] candles after weekday filter: {len(closes)} (raw {data['raw_count']})")
    if len(closes) < 30:
        raise RuntimeError(f"Only {len(closes)} usable candles — need at least 30. meta: {data['meta']}")

    now = datetime.now(timezone.utc)
    last_open = datetime.strptime(times[-1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    i = len(closes) - 1 if last_open + BAR <= now else len(closes) - 2
    bar_time = times[i]
    bar_close_time = datetime.strptime(bar_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) + BAR

    rsi_fast = rsi(closes, RSI_FAST)
    rsi_slow = rsi(closes, RSI_SLOW)
    atr14 = atr(highs, lows, closes, 14)

    sig = dual_rsi_signal(rsi_fast[i - 1], rsi_fast[i], rsi_slow[i])
    print(f"[scalp] candle {bar_time} UTC close={closes[i]:.2f} "
          f"RSI(5) {rsi_fast[i - 1]:.1f}->{rsi_fast[i]:.1f} RSI(14)={rsi_slow[i]:.1f} -> {sig.label}")

    state = load_state()

    if sig.tone == "flat":
        print("[scalp] no setup, no alert")
    elif now - bar_close_time > STALE_AFTER:
        print(f"[scalp] setup is on an old candle ({bar_time}) — market closed or data delayed, not alerting")
    elif state.get("last_alert_bar") == bar_time:
        print("[scalp] already alerted for this candle")
    else:
        trade = scalp_trade(sig.tone, closes[i], atr14[i])
        lagos_time = (bar_close_time + timedelta(hours=1)).strftime("%H:%M")
        lines = [
            f"*XAU/USD M15 — {trade.action} setup*",
            f"Candle closed {lagos_time} (Lagos) at `{closes[i]:.2f}`",
            f"RSI(5): `{rsi_fast[i - 1]:.1f}` -> `{rsi_fast[i]:.1f}`   RSI(14): `{rsi_slow[i]:.1f}`",
            "",
            f"*{trade.action}* near `{trade.entry:.2f}`",
            f"Stop-loss: `{trade.stop:.2f}`",
            f"Take-profit: `{trade.target:.2f}`",
            "",
            "Prices come from Twelve Data and can differ by a few points from your broker. "
            "Not financial advice.",
        ]
        send_telegram(bot_token, chat_id, "\n".join(lines))
        state["last_alert_bar"] = bar_time
        print("[scalp] alert sent")

    state["last_checked_bar"] = bar_time
    state["tone"] = sig.tone
    save_state(state)


if __name__ == "__main__":
    main()
