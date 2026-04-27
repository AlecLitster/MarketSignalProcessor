# MarketSignalProcessor

A multi-source technical-analysis signal processor for stocks and ETFs. Runs on a configurable polling cycle (default 15 min), computes a weighted consensus BUY / SELL / HOLD signal, detects momentum swings, generates a Claude AI synopsis, and serves a live web dashboard.

---

## Pipeline

Each cycle runs the following stages for every configured ticker:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. FETCH                                                       │
│                                                                 │
│     TradingView  ──  daily + weekly candles via tradingview_ta  │
│     YFinance     ──  1 year of daily OHLCV + pandas_ta          │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────┐
│  2. SCORE  (per source)                                         │
│                                                                 │
│     Each indicator is independently scored → [-1.0, +1.0]      │
│     Scores are weighted within each source to produce a single  │
│     source score, also in [-1.0, +1.0]                         │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────┐
│  3. AGGREGATE  (consensus)                                      │
│                                                                 │
│     Weighted average across active sources:                     │
│       TradingView   60%                                         │
│       YFinance      40%                                         │
│                                                                 │
│     Missing source → its weight is redistributed proportionally │
│                                                                 │
│     score ≥  0.30  →  BUY                                      │
│     score ≤ -0.30  →  SELL                                      │
│     otherwise      →  HOLD                                      │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────┐
│  4. SWING DETECTION                                             │
│                                                                 │
│     Compares the current consensus score against the rolling    │
│     average of the last 5 cycles in the per-ticker history.     │
│                                                                 │
│     STRONG_SWING   |delta| ≥ 0.50                              │
│     WEAK_SWING     |delta| ≥ 0.35                              │
│     SCORE_SWING    |delta| ≥ 0.25                              │
│     SIGNAL_CHANGE  BUY / SELL / HOLD label flipped             │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────┐
│  5. AI SYNOPSIS  (Claude)                                       │
│                                                                 │
│     Skipped for HOLD with no swing event (saves API tokens).   │
│     Claude receives: current signals, indicator values,         │
│     swing context, and the last 10 cycles of history.          │
│     Produces: signal, confidence, price target range,           │
│     target date range, reasoning, key factors.                  │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────┐
│  6. PERSIST                                                     │
│                                                                 │
│     logs/tickers/<TICKER>.json  — full CycleResult history     │
│     logs/signals.csv            — flat CSV, rotated at 10 MB   │
│     logs/ai_prompt.txt          — raw indicator prompt for LLMs │
│     Dashboard push              — http://127.0.0.1:5000        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Trading Signals

### Signal vocabulary

| Signal | Meaning |
|---|---|
| **BUY** | Consensus score ≥ 0.30 |
| **SELL** | Consensus score ≤ −0.30 |
| **HOLD** | Consensus score between −0.30 and +0.30 |

Scores are normalised to **−1.0 → +1.0** at every stage. A score of +1.0 means every indicator across every active source is strongly bullish.

### Consensus weights

| Source | Weight | Description |
|---|---|---|
| TradingView | 60% | Aggregated buy/sell/neutral counts across daily and weekly timeframes |
| YFinance | 40% | pandas_ta indicators computed from 1 year of daily OHLCV data |

When a source fails or is disabled its weight is redistributed proportionally to the remaining sources so the score always represents the full range.

### TradingView indicators (daily + weekly)

TradingView's own recommendation engine is used. It counts buy/sell/neutral votes across a broad indicator set (MAs, RSI, MACD, Stochastic, CCI, ADX, Momentum, Williams %R, VWMA, Hull MA, Ichimoku) and the result is mapped to a source score.

Timeframe weights: daily 62.5%, weekly 37.5%.

### YFinance indicators (pandas_ta)

| Category | Indicators |
|---|---|
| Moving averages | SMA 20 / 50 / 200, EMA 9 / 21 |
| Oscillators | RSI 14, MACD 12/26/9, Stochastic 14/3/3 |
| Trend | ADX 14, Bollinger Bands 20/2 |
| Volume | OBV trend |

Each indicator is scored independently, then combined with category weights to form the YFinance source score.

### Swing detection

Swing events are a secondary alarm layer on top of the consensus signal. They fire when the current score diverges significantly from the recent rolling average, regardless of whether the BUY/SELL/HOLD label changed:

| Label | Trigger |
|---|---|
| `STRONG_SWING` | |delta| ≥ 0.50 |
| `WEAK_SWING` | |delta| ≥ 0.35 |
| `SCORE_SWING` | |delta| ≥ 0.25 |
| `SIGNAL_CHANGE` | Label flipped, delta below all thresholds |

Swing events are included in the AI prompt and highlighted on the dashboard.

### AI synopsis (Claude)

Claude receives the full signal context and produces:

- **Signal** — BUY / SELL / HOLD
- **Confidence** — HIGH / MEDIUM / LOW (LOW always becomes HOLD)
- **Price target** — point estimate + low/high range (BUY/SELL only)
- **Target date range** — e.g. `2026-05-15 to 2026-06-01`
- **Reasoning** — 2–3 sentence synthesis
- **Key bullish factors** / **key bearish risks**
- **Entry suggestion** / **stop-loss suggestion**

---

## Project Structure

```
MarketSignalProcessor/
├── main.py                        # Orchestrator and polling loop
├── config/
│   ├── settings.py                # All env-driven settings with defaults
│   ├── indicators_tradingview.py  # TV indicator registry and scoring functions
│   └── indicators_yfinance.py     # YF indicator registry, weights, and scoring
├── core/
│   ├── models.py                  # Data contracts — CycleResult, SourceSignal, etc.
│   ├── aggregator.py              # Weighted consensus computation
│   └── swing.py                   # Swing event detection
├── sources/
│   ├── base.py                    # SignalSource ABC
│   ├── tradingview.py             # TradingView adapter (tradingview_ta)
│   └── yfinance_source.py         # YFinance + pandas_ta adapter
├── ai/
│   ├── base.py                    # AIInterpreter ABC
│   └── claude.py                  # Claude API interpreter
├── brokers/
│   ├── base.py                    # Broker ABC
│   └── schwab.py                  # Schwab scaffold (stubs only — not live)
├── stores/
│   ├── ticker_store.py            # Per-ticker JSON history store
│   ├── csv_log.py                 # Flat CSV log with rotation
│   └── ai_prompt_log.py           # Raw indicator dump for external LLM use
└── dashboard/
    ├── server.py                  # Flask HTTP server
    └── static/
        ├── index.html
        ├── style.css
        └── app.js
```

---

## Setup

### Prerequisites

- Python 3.10+
- Claude API key (only required when `CLAUDE_AI_SYNOPSIS_ENABLED=true`)

### Install

```bash
pip install flask tradingview_ta yfinance pandas_ta python-dotenv requests
```

### Configure

Copy `.env.example` to `.env` and fill in secrets. Key variables:

```env
# API keys
CLAUDE_API_KEY=sk-ant-...

# Feature flags
TRADINGVIEW_ENABLED=true
YFINANCE_ENABLED=true
CLAUDE_AI_SYNOPSIS_ENABLED=true
TRADING_ENABLED=false          # keep false — Schwab broker is unimplemented

# Polling
POLLING_INTERVAL_SECONDS=900   # 15 minutes

# Signal thresholds
BUY_THRESHOLD=0.30
SELL_THRESHOLD=-0.30

# Consensus weights (must sum to 1.0)
# Set via CONSENSUS_WEIGHTS in config/settings.py

# Dashboard
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=5000

# Claude
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=1024

# YFinance history window
YF_PERIOD=1y
YF_INTERVAL=1d

# TradingView rate-limit delays (seconds)
TV_TICKER_DELAY_SEC=1.0
TV_STARTUP_DELAY_SEC=1.0
```

### Tickers

Edit `TICKERS` in [config/settings.py](config/settings.py):

```python
TICKERS = [
    {"symbol": "SPY",  "exchange": "AMEX"},
    {"symbol": "QQQ",  "exchange": "NASDAQ"},
    {"symbol": "MSFT", "exchange": "NASDAQ"},
]
```

---

## Running

```bash
python main.py
```

The dashboard starts automatically in a background thread. Open **http://127.0.0.1:5000**.

Console output per cycle:

```
2026-04-26 14:00:00  INFO  main  ━━━ Cycle start (9 tickers) ━━━
2026-04-26 14:00:02  INFO  main  SPY      BUY   score=+0.4120  TV=BUY   YF=BUY   AI=BUY   swing=—
2026-04-26 14:00:03  INFO  main  QQQ      HOLD  score=+0.1840  TV=BUY   YF=HOLD  AI=HOLD  swing=—
...
2026-04-26 14:00:18  INFO  main  ━━━ Cycle done ━━━
```

---

## Dashboard

| Endpoint | Description |
|---|---|
| `GET /` | Live dashboard UI |
| `GET /api/signals` | Latest signal summary for every ticker |
| `GET /api/history/<TICKER>` | Full per-ticker history from the JSON store |
| `GET /api/status` | Service metadata (uptime, ticker count) |

The summary table shows: TradingView signal + score, YFinance signal + score, AI signal + confidence + price target, consensus signal + score, swing label, timestamp.

Clicking any row opens the per-ticker history panel showing the last N cycles.

---

## Data Models

All pipeline stages communicate through typed dataclasses in [core/models.py](core/models.py):

| Type | Description |
|---|---|
| `SourceSignal` | Normalised output from one source — score, signal, indicator breakdown |
| `AISignal` | Claude synopsis — signal, confidence, price target, reasoning |
| `SwingEvent` | Detected momentum swing — delta, label, which sources changed |
| `CycleResult` | Complete output for one ticker in one cycle; written to all stores |

---

## Storage

| Path | Format | Notes |
|---|---|---|
| `logs/tickers/<TICKER>.json` | JSON array | Full `CycleResult` history, capped at `MAX_TICKER_HISTORY_CYCLES` (default 500) |
| `logs/signals.csv` | CSV | Flat signal log rotated at 10 MB with up to 5 compressed backups |
| `logs/ai_prompt.txt` | Plain text | Raw indicator values formatted for pasting into any LLM — no scores or labels included |

---

## Extending

**Add a ticker** — edit `TICKERS` in `config/settings.py`.

**Add a signal source** — implement `SignalSource` from `sources/base.py`, add its key to `CONSENSUS_WEIGHTS` in `config/settings.py`, and wire it into `_fetch_one()` in `main.py`.

**Tune consensus weights** — edit `CONSENSUS_WEIGHTS` in `config/settings.py`; missing sources are redistributed automatically.

**Tune swing sensitivity** — adjust the `SWING_SCORE_*_THRESHOLD` variables in `.env`.

**Broker integration** — `brokers/schwab.py` is a complete scaffold. Implement `_authenticate()` and the order methods, then set `TRADING_ENABLED=true` only after thorough sandbox testing.
