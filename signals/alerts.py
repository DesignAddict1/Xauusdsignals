"""Telegram delivery for signal alerts."""

import requests


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Telegram send failed: {resp.status_code} {resp.text}")
