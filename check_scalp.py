#!/usr/bin/env python3
"""Live dual-RSI scalping alerts for XAU/USD, run every 3 minutes.

Entries come from the M15 chart: RSI(14) for direction, RSI(5) for timing.
  * LIVE alert  - as soon as RSI(5) turns on the candle that is still forming.
  * CONFIRMED / CANCELLED - when that candle closes, says whether it held.
  * Candle-close alert - if RSI(5) only turned in the last minutes before the
                  close (between two checks), you still get the alert at close.
Times are in UTC (the market clock) with Lagos time alongside."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.data import fetch_series
from signals.indicators import rsi, atr
from signals.rules import (dual_rsi_signal, scalp_trade, RSI_FAST, RSI_SLOW,
                           SCALP_STOP_ATR, SCALP_TARGET_ATR)
from signals.alerts import send_telegram
from signals.state import STATE_DIR

STATE_FILE = os.path.join(STATE_DIR, "scalp.json")
M15 = timedelta(minutes=15)
STALE_AFTER = timedelta(minutes=20)
LATE_ATR = 0.5
HIGHER_TFS = [("M30", "30min", timedelta(minutes=30)), ("H1", "1h", timedelta(hours=1))]
RR = f"Risk:reward `1:{SCALP_TARGET_ATR / SCALP_STOP_ATR:g}`"
FOOTER = "Prices come from Twelve Data and can differ by a few points from your broker. Not financial advice."


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


def clock(t: datetime) -> str:
    return f"{t:%H:%M} UTC ({t + timedelta(hours=1):%H:%M} Lagos)"


def last_closed_index(times, bar: timedelta, at: datetime) -> int:
    for k in range(len(times) - 1, -1, -1):
        if to_utc(times[k]) + bar <= at:
            return k
    return -1


def bias(r14) -> str:
    if r14 is None:
        return "no data"
    return "bullish" if r14 > 50 else "bearish" if r14 < 50 else "neutral"


def confidence(side: str, higher: list) -> tuple:
    want = "bullish" if side == "BUY" else "bearish"
    agree = sum(1 for tf in higher if tf["bias"] == want)
    labels = {2: "Strong — M30 and H1 both agree",
              1: "Moderate — one higher timeframe agrees",
              0: "Weak — M30 and H1 don't agree"}
    return agree, labels[agree]


def higher_timeframes(api_key: str, at: datetime) -> list:
    out = []
    for name, interval, bar in HIGHER_TFS:
        d = fetch_series("XAU/USD", interval, 300, api_key)
        k = last_closed_index(d["times"], bar, at)
        r5, r14 = rsi(d["closes"], RSI_FAST), rsi(d["closes"], RSI_SLOW)
        if k < 0 or r14[k] is None:
            out.append({"name": name, "r5": None, "r14": None, "bias": "no data"})
            continue
        out.append({"name": name, "r5": r5[k], "r14": r14[k], "bias": bias(r14[k])})
        print(f"[scalp] {name} candle {d['times'][k]} RSI(5)={r5[k]:.1f} RSI(14)={r14[k]:.1f} {bias(r14[k])}")
    return out


def report_lines(m15_line: str, higher: list, side: str) -> list:
    agree, text = confidence(side, higher)
    lines = ["*Timeframe report*", m15_line]
    for tf in higher:
        if tf["r14"] is None:
            lines.append(f"{tf['name']}: no data")
        else:
            lines.append(f"{tf['name']}: RSI(5) `{tf['r5']:.1f}`, RSI(14) `{tf['r14']:.1f}` ({tf['bias']})")
    lines.append(f"Confidence: *{text}*")
    return lines


def moved_line(side: str, ref: float, price_now: float, atr_val: float, since: str) -> list:
    moved = (price_now - ref) if side == "BUY" else (ref - price_now)
    lines = [f"Price now `{price_now:.2f}` ({moved:+.2f} in the trade's direction since {since})"]
    if atr_val and moved >= LATE_ATR * atr_val:
        lines.append(f"Late: price has already run {moved:.2f} points. Consider waiting for a pullback "
                     "instead of chasing.")
    return lines


def main():
    api_key = os.environ["TWELVE_DATA_KEY"]
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    send = lambda lines: send_telegram(bot_token, chat_id, "\n".join(lines))

    data = fetch_series("XAU/USD", "15min", 300, api_key)
    closes, highs, lows, times = data["closes"], data["highs"], data["lows"], data["times"]
    n = len(closes)
    print(f"[scalp] M15 candles in market hours: {n} (raw {data['raw_count']})")
    if n < 30:
        raise RuntimeError(f"Only {n} usable candles — need at least 30. meta: {data['meta']}")

    now = datetime.now(timezone.utc)
    state = load_state()
    if "last_alert_bar" in state and "closed_done" not in state:
        state["closed_done"] = state["last_alert_bar"]

    newest_open = to_utc(times[-1])
    if now - newest_open > M15 + STALE_AFTER:
        print(f"[scalp] newest candle is {times[-1]} UTC — market closed or data delayed, nothing to do")
        save_state(state)
        return

    forming = newest_open + M15 > now
    c = n - 2 if forming else n - 1
    f = n - 1 if forming else None
    price_now = closes[-1]

    r5 = rsi(closes, RSI_FAST)
    r14 = rsi(closes, RSI_SLOW)
    a14 = atr(highs, lows, closes, 14)

    # 1) The candle that just closed
    c_close = to_utc(times[c]) + M15
    sig_c = dual_rsi_signal(r5[c - 1], r5[c], r14[c])
    print(f"[scalp] closed {times[c]} UTC close={closes[c]:.2f} "
          f"RSI(5) {r5[c - 1]:.1f}->{r5[c]:.1f} RSI(14)={r14[c]:.1f} -> {sig_c.label}")

    if state.get("closed_done") != times[c] and now - c_close <= STALE_AFTER:
        live = state.get("live") or {}
        if live.get("bar") == times[c]:
            held = (sig_c.tone == "up") == (live["side"] == "BUY") and sig_c.tone != "flat"
            if held:
                send([f"*CONFIRMED — {live['side']} held at the {clock(c_close)} close*",
                      f"RSI(5) closed at `{r5[c]:.1f}`, RSI(14) `{r14[c]:.1f}`",
                      f"Candle closed at `{closes[c]:.2f}`, live alert was at `{live['entry']:.2f}`",
                      *moved_line(live["side"], live["entry"], price_now, a14[-1], "the live alert")])
                print("[scalp] sent CONFIRMED")
            else:
                need = "30 or above" if live["side"] == "BUY" else "70 or below"
                send([f"*CANCELLED — the {live['side']} from {live['time']} did not hold*",
                      f"RSI(5) closed at `{r5[c]:.1f}` (needed {need}), RSI(14) `{r14[c]:.1f}`",
                      f"Price now `{price_now:.2f}`. If you're in the trade, manage it by your own rules."])
                print("[scalp] sent CANCELLED")
        elif sig_c.tone != "flat":
            trade = scalp_trade(sig_c.tone, closes[c], a14[c])
            higher = higher_timeframes(api_key, c_close)
            send([f"*{trade.action} setup — XAU/USD M15 (at candle close)*",
                  f"Candle closed {clock(c_close)} at `{closes[c]:.2f}`",
                  *moved_line(trade.action, closes[c], price_now, a14[c], "the close"),
                  "",
                  f"*{trade.action}* near `{trade.entry:.2f}`",
                  f"Stop-loss: `{trade.stop:.2f}`",
                  f"Take-profit: `{trade.target:.2f}`",
                  RR,
                  "",
                  *report_lines(f"M15: RSI(5) `{r5[c - 1]:.1f}` -> `{r5[c]:.1f}`, RSI(14) `{r14[c]:.1f}`",
                                higher, trade.action),
                  "", FOOTER])
            print("[scalp] sent candle-close alert")
        state["closed_done"] = times[c]

    # 2) The candle still forming: LIVE alert the moment RSI(5) turns (once per candle)
    if f is not None:
        sig_f = dual_rsi_signal(r5[f - 1], r5[f], r14[f])
        print(f"[scalp] live {times[f]} UTC price={price_now:.2f} "
              f"RSI(5) {r5[f - 1]:.1f}->{r5[f]:.1f} RSI(14)={r14[f]:.1f} -> {sig_f.label}")
        live = state.get("live") or {}
        if sig_f.tone != "flat" and live.get("bar") != times[f]:
            trade = scalp_trade(sig_f.tone, price_now, a14[f])
            f_close = to_utc(times[f]) + M15
            higher = higher_timeframes(api_key, now)
            send([f"*LIVE {trade.action} — XAU/USD M15*",
                  f"Signal at {clock(now)}, candle closes {clock(f_close)}",
                  "",
                  f"*{trade.action}* near `{trade.entry:.2f}` (price now)",
                  f"Stop-loss: `{trade.stop:.2f}`",
                  f"Take-profit: `{trade.target:.2f}`",
                  RR,
                  "",
                  *report_lines(f"M15 (live): RSI(5) `{r5[f - 1]:.1f}` -> `{r5[f]:.1f}`, RSI(14) `{r14[f]:.1f}`",
                                higher, trade.action),
                  "",
                  "Early alert: this M15 candle hasn't closed yet. You'll get CONFIRMED or CANCELLED when it closes.",
                  FOOTER])
            state["live"] = {"bar": times[f], "side": trade.action, "entry": price_now,
                             "time": clock(now)}
            print("[scalp] sent LIVE alert")

    state["last_checked_bar"] = times[c]
    save_state(state)


if __name__ == "__main__":
    main()
