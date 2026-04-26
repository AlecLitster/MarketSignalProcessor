# MarketSignalProcessor

A multi-source technical-analysis signal processor for stocks and ETFs. It polls on a configurable cycle (default 15 min), computes a weighted consensus signal, detects momentum swings, generates a Claude AI synopsis, and exposes a live web dashboard.

---

## How It Works

Each polling cycle runs this pipeline for every configured ticker:

```
1. Fetch  → TradingView  (tradingview_ta)
            BarChart Opinion  (web scrape)
            BarChart TrendSpotter  (web scrape)
            yfinance + pandas_ta  (OHLCV + indicators)

2. Score  → Each source produces a normalised score in [-1.0, +1.0]

3. Aggregate → Weighted consensus across active sources
               Missing sources: weight redistributed proportionally

4. Swing detection → Compare consensus score vs. rolling history baseline
                     Labels: STRONG_SWING / WEAK_SWING / SCORE_SWING / SIGNAL_CHANGE

5. AI synopsis → Claude interprets the full signal picture
                 Skipped for confident HOLDs with no swing (saves tokens)

6. Persist → Per-ticker JSON store  (logs/tickers/<TICKER>.json)
             Flat CSV with rotation  (logs/signals.csv)
             Live dashboard push     (http://127.0.0.1:5000)
```

### Consensus weights (default)

| Source | Weight |
|---|---|
| TradingView | 35% |
| BarChart Opinion | 25% |
| TrendSpotter | 20% |
| yfinance / pandas_ta | 20% |

Signal thresholds: `score ≥ 0.30` → **BUY**, `score ≤ -0.30` → **SELL**, else **HOLD**.

---

## Project Structure

```
MarketSignalProcessor/
├── main.py                     # Orchestrator — entry point
├── config/
│   ├── settings.py             # All env-driven settings with defaults
│   ├── indicators_tradingview.py
│   ├── indicators_barchart.py
│   └── indicators_yfinance.py
├── core/
│   ├── models.py               # Data contracts (CycleResult, SourceSignal, etc.)
│   ├── aggregator.py           # Weighted consensus computation
│   └── swing.py                # Swing event detection
├── sources/
│   ├── base.py                 # SignalSource ABC
│   ├── tradingview.py          # TradingView adapter
│   ├── barchart.py             # BarChart Opinion + TrendSpotter adapter
│   └── yfinance_source.py      # yfinance + pandas_ta adapter
├── ai/
│   ├── base.py                 # AIInterpreter ABC
│   └── claude.py               # Claude API interpreter
├── brokers/
│   ├── base.py                 # Broker ABC
│   └── schwab.py               # Schwab scaffold (all stubs — not yet live)
├── stores/
│   ├── ticker_store.py         # Per-ticker JSON history
│   └── csv_log.py              # Flat CSV with rotation
└── dashboard/
    ├── server.py               # Flask HTTP server
    └── static/
        ├── index.html
        ├── style.css
        └── app.js
```

---

## Setup

### Prerequisites

- Python 3.10+
- A Claude API key (only required when `CLAUDE_AI_SYNOPSIS_ENABLED=true`)

### Install dependencies

```bash
pip install flask tradingview_ta yfinance pandas_ta python-dotenv requests
```

### Configure environment

Copy `.env` to your own and fill in secrets:

```bash
cp .env .env.local   # or edit .env directly — it is gitignored
```

Key variables (all optional — sensible defaults are shown):

```env
# API keys
CLAUDE_API_KEY=sk-ant-...

# Feature flags
TRADINGVIEW_ENABLED=true
BARCHART_ENABLED=false
YFINANCE_ENABLED=true
CLAUDE_AI_SYNOPSIS_ENABLED=true
TRADING_ENABLED=false          # KEEP FALSE until Schwab broker is implemented

# Polling
POLLING_INTERVAL_SECONDS=900   # 15 minutes

# Signal thresholds
BUY_THRESHOLD=0.30
SELL_THRESHOLD=-0.30

# Dashboard
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=5000

# Claude model
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=1024

# Storage
LOG_DIR=logs
MAX_TICKER_HISTORY_CYCLES=500

# TradingView rate-limit courtesy delays (seconds)
TV_TICKER_DELAY_SEC=1.0
TV_STARTUP_DELAY_SEC=1.0

# yfinance
YF_PERIOD=1y
YF_INTERVAL=1d

# Schwab (only needed when TRADING_ENABLED=true)
SCHWAB_API_KEY=
SCHWAB_API_SECRET=
SCHWAB_ACCOUNT_ID=
```

### Tickers

Edit `TICKERS` in [config/settings.py](config/settings.py):

```python
TICKERS = [
    {"symbol": "SPY",  "exchange": "AMEX"},
    {"symbol": "QQQ",  "exchange": "NASDAQ"},
    # ...
]
```

---

## Running

```bash
python main.py
```

The dashboard starts automatically in a background thread. Open **http://127.0.0.1:5000** in a browser.

Console output per cycle:

```
2026-04-26 14:00:00  INFO     main  ━━━ Cycle start (6 tickers) ━━━
2026-04-26 14:00:02  INFO     main  SPY      BUY   score=+0.4120  TV=BUY   BC=N/A  TS=N/A  YF=BUY  AI=BUY  swing=—
...
2026-04-26 14:00:10  INFO     main  ━━━ Cycle done ━━━
```

---

## Dashboard API

All endpoints return JSON.

| Endpoint | Description |
|---|---|
| `GET /` | Live dashboard UI |
| `GET /api/signals` | Latest signal summary for every ticker |
| `GET /api/history/<TICKER>` | Full per-ticker history (from JSON store) |
| `GET /api/status` | Service metadata (uptime, ticker count) |

---

## Data Models

All pipeline stages communicate through typed dataclasses defined in [core/models.py](core/models.py):

| Type | Description |
|---|---|
| `SourceSignal` | Normalised output from one source (score, signal, indicators) |
| `TrendSpotterSignal` | BarChart TrendSpotter — strength + change direction |
| `AISignal` | Claude synopsis — signal, confidence, price target, reasoning |
| `SwingEvent` | Momentum swing — delta, label, which sources changed |
| `CycleResult` | Everything for one ticker in one cycle; written to all stores |

---

## Feature Flags

All flags are env-driven and default to a safe read-only configuration:

| Flag | Default | Notes |
|---|---|---|
| `TRADINGVIEW_ENABLED` | `true` | Requires no API key |
| `BARCHART_ENABLED` | `false` | Web scrape — use sparingly |
| `YFINANCE_ENABLED` | `true` | Free, no key needed |
| `CLAUDE_AI_SYNOPSIS_ENABLED` | `true` | Requires `CLAUDE_API_KEY` |
| `TRADING_ENABLED` | `false` | **Must stay false** — Schwab broker is unimplemented stubs |

---

## Broker Status

`brokers/schwab.py` is a complete scaffold with no live implementation. No orders will ever be placed while `TRADING_ENABLED=false` (the default). Before enabling trading:

1. Implement `_authenticate()` in `schwab.py` using OAuth2
2. Replace all stub methods with real Schwab API calls
3. Set `SCHWAB_API_KEY`, `SCHWAB_API_SECRET`, `SCHWAB_ACCOUNT_ID` in `.env`
4. Test thoroughly in paper/sandbox mode before setting `TRADING_ENABLED=true`

Reference: https://developer.schwab.com

---

## Storage

| Path | Format | Notes |
|---|---|---|
| `logs/tickers/<TICKER>.json` | JSON array | Full `CycleResult` history, capped at `MAX_TICKER_HISTORY_CYCLES` entries |
| `logs/signals.csv` | CSV | Flat signal log; rotated at `LOG_CSV_MAX_BYTES` (default 10 MB) |

---

## Extending

**Add a ticker** — edit `TICKERS` in `config/settings.py`.

**Add a signal source** — implement `SignalSource` ABC from `sources/base.py`, add a weight in `CONSENSUS_WEIGHTS`, and wire it into `main.py`.

**Change consensus weights** — edit `CONSENSUS_WEIGHTS` in `config/settings.py`; weights are redistributed automatically when a source is unavailable.

**Tune swing sensitivity** — adjust `SWING_SCORE_DELTA_THRESHOLD`, `SWING_SCORE_WEAK_DELTA_THRESHOLD`, `SWING_SCORE_STRONG_DELTA_THRESHOLD` in `.env`.
