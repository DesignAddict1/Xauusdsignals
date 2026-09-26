# XAU/USD Signal Desk

A rule-based gold (XAU/USD) signal system with two parts:

1. **Dashboard** (`docs/index.html`) — an on-demand view of the monthly trend and 15-min
   scalping signal, plus a backtester that runs the same rules against real historical data.
2. **Automated alerts** (`check_scalp.py`, `check_monthly.py`) — scripts that run on a schedule
   via GitHub Actions and message you on Telegram whenever a signal flips. No server to
   maintain — GitHub runs them for free.

Both use the exact same indicator math (`signals/indicators.py`, `signals/rules.py`), so the
dashboard, the backtest, and the Telegram alert always agree.

## How the signals work

- **Monthly trend** (daily candles): EMA50 vs EMA200 + RSI(14). Bullish when EMA50 is above
  EMA200 and RSI is above 50; bearish on the mirror image; neutral otherwise.
- **Scalping** (15-min candles): EMA9 vs EMA21 + RSI(14), with overbought/oversold caution
  flags outside the 25–75 RSI band.
- **Trade call**: entry zone, stop-loss and take-profit, sized off ATR(14) at roughly a 1:2
  risk-reward.

None of this is a guarantee — see the "Being honest about accuracy" section below.

## One-time setup (about 10 minutes)

### 1. Get a free Twelve Data API key
Sign up at [twelvedata.com](https://twelvedata.com) (free tier, no card required) and copy
your API key from the dashboard.

### 2. Create a Telegram bot
1. In Telegram, message **@BotFather** and send `/newbot`.
2. Follow the prompts (pick a name and a username ending in `bot`).
3. BotFather replies with a token like `123456789:AAExampleTokenHere` — copy it.
4. Send your new bot any message (e.g. "hi") so it can message you back.
5. Get your chat ID: message **@userinfobot** and it will reply with your numeric ID.
   (Or visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` after step 4 and read
   `"chat":{"id": ...}` from the JSON.)

### 3. Push this project to your own GitHub repo
```bash
cd xauusd-signals
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/xauusd-signals.git
git push -u origin main
```

### 4. Add your secrets to the repo
On GitHub: **Settings → Secrets and variables → Actions → New repository secret**. Add three:

| Secret name | Value |
|---|---|
| `TWELVE_DATA_KEY` | your Twelve Data API key |
| `TELEGRAM_BOT_TOKEN` | your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | your numeric chat ID |

### 5. Enable Actions
Go to the **Actions** tab of your repo and enable workflows if prompted. That's it — from
here the two workflows run on their own schedule:

- `.github/workflows/scalp.yml` — every 15 minutes
- `.github/workflows/monthly.yml` — once a day on weekdays

Each run commits its own tiny state file back to the repo (`state/*.json`) so it remembers
the last signal and only messages you when something actually changes.

### 6. (Optional) Publish the dashboard
Settings → Pages → deploy from branch `main`, folder `/docs`. You'll get a URL like
`https://<your-username>.github.io/xauusd-signals/` for the live dashboard + backtester.

## Running locally (optional, for testing)
```bash
pip install -r requirements.txt
export TWELVE_DATA_KEY=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python check_scalp.py
python check_monthly.py
```

## Tuning the rules
All thresholds live in `signals/rules.py`. If the dashboard's backtest panel shows a poor
win rate or negative expectancy, this is the file to adjust — e.g. tighten the RSI band,
change the EMA periods, or adjust the ATR multiples in `trade_call()`. Re-run the dashboard's
backtest after each change to see the effect before it goes live.

## Being honest about accuracy
No technical rule set reliably hits 80%+ accuracy on gold, especially intraday — if it did,
it would stop working once enough people traded it. Use the backtest panel in the dashboard
to see this rule set's *real* historical win rate and expectancy, and treat a good backtest
as "worth testing live with small size," not a guarantee. Markets change regime, so
performance on past data is not a promise of future performance. This project is a
decision-support tool, not financial advice.
