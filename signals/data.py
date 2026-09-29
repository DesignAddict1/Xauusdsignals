"""Twelve Data fetch. Candles are kept only for gold's real trading week
(Sunday evening open to Friday evening close, UTC), matching the dashboard."""

from datetime import datetime
from typing import Dict, List
import requests

BASE_URL = "https://api.twelvedata.com/time_series"


def is_market_bar(row: dict) -> bool:
    """Gold trades from about 22:00 UTC Sunday to about 21:00-22:00 UTC Friday.
    Twelve Data fills the closed weekend with placeholder candles; drop those,
    and any candle with no price movement at all (high == low)."""
    s = row["datetime"]
    d = datetime.strptime(s[:10], "%Y-%m-%d")
    hour = int(s[11:13]) if len(s) >= 13 else 0
    wd = d.weekday()  # Mon=0 ... Fri=4, Sat=5, Sun=6
    if wd == 5:
        return False
    if wd == 6 and hour < 21:
        return False
    if wd == 4 and hour >= 22:
        return False
    return float(row["high"]) != float(row["low"])


def is_weekday(dt_str: str) -> bool:  # kept for older callers
    return datetime.strptime(dt_str[:10], "%Y-%m-%d").weekday() < 5


def fetch_series(symbol: str, interval: str, outputsize: int, api_key: str) -> Dict[str, List[float]]:
    resp = requests.get(
        BASE_URL,
        params={
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "timezone": "UTC",
            "apikey": api_key,
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("status") == "error" or data.get("code"):
        raise RuntimeError(data.get("message", "Twelve Data API error"))
    if "values" not in data:
        raise RuntimeError(f"No 'values' in response — raw response: {data}")

    raw_count = len(data["values"])
    rows = list(reversed(data["values"]))  # oldest -> newest
    rows = [r for r in rows if is_market_bar(r)]

    return {
        "closes": [float(r["close"]) for r in rows],
        "highs": [float(r["high"]) for r in rows],
        "lows": [float(r["low"]) for r in rows],
        "times": [r["datetime"] for r in rows],
        "raw_count": raw_count,
        "meta": data.get("meta", {}),
    }
