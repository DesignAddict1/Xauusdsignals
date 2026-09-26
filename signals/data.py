"""Twelve Data fetch, with the same weekend-timestamp filter as the
dashboard so both stay in sync."""

from datetime import datetime
from typing import Dict, List
import requests

BASE_URL = "https://api.twelvedata.com/time_series"


def is_weekday(dt_str: str) -> bool:
    d = datetime.strptime(dt_str[:10], "%Y-%m-%d")
    return d.weekday() < 5  # Mon=0 ... Sun=6, drop Sat/Sun


def fetch_series(symbol: str, interval: str, outputsize: int, api_key: str) -> Dict[str, List[float]]:
    resp = requests.get(
        BASE_URL,
        params={
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": api_key,
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("status") == "error" or data.get("code"):
        raise RuntimeError(data.get("message", "Twelve Data API error"))
    if "values" not in data:
        # Free-tier plan limits sometimes come back as status "ok" with no
        # values and an explanatory message instead of an error code.
        raise RuntimeError(f"No 'values' in response — raw response: {data}")

    raw_count = len(data["values"])
    rows = list(reversed(data["values"]))  # oldest -> newest
    rows = [r for r in rows if is_weekday(r["datetime"])]

    return {
        "closes": [float(r["close"]) for r in rows],
        "highs": [float(r["high"]) for r in rows],
        "lows": [float(r["low"]) for r in rows],
        "times": [r["datetime"] for r in rows],
        "raw_count": raw_count,
        "meta": data.get("meta", {}),
    }
