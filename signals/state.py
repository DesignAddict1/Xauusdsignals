"""Tiny JSON state store — remembers the last signal we alerted on, so
we only ping Telegram when the signal actually changes, not every run."""

import json
import os
from typing import Optional

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")


def _path(name: str) -> str:
    return os.path.join(STATE_DIR, f"{name}.json")


def load_last_tone(name: str) -> Optional[str]:
    path = _path(name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get("tone")


def save_last_tone(name: str, tone: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_path(name), "w") as f:
        json.dump({"tone": tone}, f)
