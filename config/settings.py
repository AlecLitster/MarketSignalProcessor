"""
config/settings.py
------------------
All runtime settings. Values are read from environment variables (or a .env
file loaded by python-dotenv) with sensible defaults.

Copy .env.example to .env and fill in API keys before running.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from tradingview_ta import Interval

load_dotenv()

# ---------------------------------------------------------------------------
# Tickers to monitor
# Each entry: {"symbol": "AAPL", "exchange": "NASDAQ"}
# ---------------------------------------------------------------------------

TICKERS: list[dict] = [
    {"symbol": "AIQ",   "exchange": "NASDAQ"},
    {"symbol": "COMB",  "exchange": "AMEX"},
    {"symbol": "COPX",  "exchange": "NYSE"},
    {"symbol": "FXE",   "exchange": "AMEX"},
    {"symbol": "GLD",   "exchange": "AMEX"},
    {"symbol": "IBIT",   "exchange": "NASDAQ"},
    {"symbol": "SPY",   "exchange": "AMEX"},
    {"symbol": "QQQ",   "exchange": "NASDAQ"},
    {"symbol": "MSFT",  "exchange": "NASDAQ"},
    {"symbol": "SLV",   "exchange": "AMEX"},
    
]

# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

POLLING_INTERVAL_SECONDS: int = int(os.environ.get("POLLING_INTERVAL_SECONDS", 900))

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

TRADINGVIEW_ENABLED:        bool = os.environ.get("TRADINGVIEW_ENABLED",        "true").lower()  == "true"
YFINANCE_ENABLED:           bool = os.environ.get("YFINANCE_ENABLED",           "true").lower()  == "true"
CLAUDE_AI_SYNOPSIS_ENABLED: bool = os.environ.get("CLAUDE_AI_SYNOPSIS_ENABLED", "true").lower()  == "true"
TRADING_ENABLED:            bool = os.environ.get("TRADING_ENABLED",            "false").lower() == "true"
ACTIVE_BROKER:              str  = os.environ.get("ACTIVE_BROKER",              "schwab")

# ---------------------------------------------------------------------------
# TradingView
# ---------------------------------------------------------------------------

TRADINGVIEW_SCREENER: str = os.environ.get("TRADINGVIEW_SCREENER", "america")

TRADINGVIEW_TIMEFRAMES: dict = {
    "daily":  Interval.INTERVAL_1_DAY,
    "weekly": Interval.INTERVAL_1_WEEK,
}

# Weights must sum to 1.0
TRADINGVIEW_TIMEFRAME_WEIGHTS: dict[str, float] = {
    "daily":  0.625,
    "weekly": 0.375,
}

TV_RETRY_ATTEMPTS:  int   = int(float(os.environ.get("TV_RETRY_ATTEMPTS",  3)))
TV_RETRY_DELAY_SEC: float = float(os.environ.get("TV_RETRY_DELAY_SEC", 1.0))
TV_CALL_DELAY_SEC:  float = float(os.environ.get("TV_CALL_DELAY_SEC",  1.0))
TV_TICKER_DELAY_SEC:  float = float(os.environ.get("TV_TICKER_DELAY_SEC",  1.0))
TV_STARTUP_DELAY_SEC: float = float(os.environ.get("TV_STARTUP_DELAY_SEC", 1.0))

# ---------------------------------------------------------------------------
# Signal scoring thresholds
# ---------------------------------------------------------------------------

BUY_THRESHOLD:  float = float(os.environ.get("BUY_THRESHOLD",   0.30))
SELL_THRESHOLD: float = float(os.environ.get("SELL_THRESHOLD", -0.30))

# TradingView RECOMMENDATION string → numeric score
SIGNAL_SCORE_MAP: dict[str, float] = {
    "STRONG_BUY":  1.00,
    "BUY":         0.50,
    "NEUTRAL":     0.00,
    "SELL":       -0.50,
    "STRONG_SELL": -1.00,
}

# ---------------------------------------------------------------------------
# Consensus weights (missing sources are redistributed proportionally)
# ---------------------------------------------------------------------------

CONSENSUS_WEIGHTS: dict[str, float] = {
    "tradingview": 0.70,
    "yfinance":    0.30,
}

# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------

SWING_HISTORY_WINDOW:               int   = int(float(os.environ.get("SWING_HISTORY_WINDOW",               5)))
SWING_MIN_HISTORY_ENTRIES:          int   = int(float(os.environ.get("SWING_MIN_HISTORY_ENTRIES",          2)))
SWING_SCORE_DELTA_THRESHOLD:        float = float(os.environ.get("SWING_SCORE_DELTA_THRESHOLD",        0.25))
SWING_SCORE_WEAK_DELTA_THRESHOLD:   float = float(os.environ.get("SWING_SCORE_WEAK_DELTA_THRESHOLD",   0.35))
SWING_SCORE_STRONG_DELTA_THRESHOLD: float = float(os.environ.get("SWING_SCORE_STRONG_DELTA_THRESHOLD", 0.50))

# ---------------------------------------------------------------------------
# yfinance + pandas_ta
# ---------------------------------------------------------------------------

YF_PERIOD:      str = os.environ.get("YF_PERIOD",      "1y")    # history window fed to pandas_ta (needs ≥200 rows for SMA_200)
YF_INTERVAL:    str = os.environ.get("YF_INTERVAL",    "1d")    # candle size (daily matches TV)
YF_MIN_PERIODS: int = int(float(os.environ.get("YF_MIN_PERIODS", 30)))  # min rows to compute SMA_200

# ---------------------------------------------------------------------------
# Claude AI
# ---------------------------------------------------------------------------

CLAUDE_API_KEY:         str = os.environ.get("CLAUDE_API_KEY",         "")
CLAUDE_MODEL:           str = os.environ.get("CLAUDE_MODEL",           "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS:      int = int(float(os.environ.get("CLAUDE_MAX_TOKENS",      1024)))
CLAUDE_TIMEOUT_SECONDS: int = int(float(os.environ.get("CLAUDE_TIMEOUT_SECONDS", 30)))
CLAUDE_MAX_RETRIES:     int = int(float(os.environ.get("CLAUDE_MAX_RETRIES",     3)))
AI_HISTORY_CYCLES:      int = int(float(os.environ.get("AI_HISTORY_CYCLES",      10)))

# ---------------------------------------------------------------------------
# Storage / logging
# ---------------------------------------------------------------------------

LOG_DIR:    str = os.environ.get("LOG_DIR", "logs")

LOG_TICKER_DIR:           str  = os.path.join(LOG_DIR, "tickers")
LOG_CSV_FILE:             str  = os.path.join(LOG_DIR, "signals.csv")
LOG_CSV_MAX_BYTES:        int  = int(float(os.environ.get("LOG_CSV_MAX_BYTES",  10 * 1024 * 1024)))
LOG_BACKUP_COUNT:         int  = int(float(os.environ.get("LOG_BACKUP_COUNT",   5)))
LOG_TICKER_JSON_ENABLED:  bool = os.environ.get("LOG_TICKER_JSON_ENABLED",  "true").lower() == "true"
LOG_CSV_ENABLED:          bool = os.environ.get("LOG_CSV_ENABLED",          "true").lower() == "true"
LOG_AI_PROMPT_ENABLED:    bool = os.environ.get("LOG_AI_PROMPT_ENABLED",    "true").lower() == "true"
LOG_AI_PROMPT_FILE:       str  = os.path.join(LOG_DIR, "ai_prompt.txt")
MAX_TICKER_HISTORY_CYCLES: int = int(float(os.environ.get("MAX_TICKER_HISTORY_CYCLES", 500)))

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HOST: str = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT: int = int(float(os.environ.get("DASHBOARD_PORT", 5000)))

# ---------------------------------------------------------------------------
# Trading safety
# ---------------------------------------------------------------------------

MAX_TRADE_SIZE_USD: float = float(os.environ.get("MAX_TRADE_SIZE_USD", 1000.0))
