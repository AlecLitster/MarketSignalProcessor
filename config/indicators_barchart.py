"""
config/indicators_barchart.py
------------------------------
Complete registry of every BarChart indicator and TrendSpotter field
processed by this system.

To add a new indicator:
  1. Find the field name from the BarChart opinion/technicals page.
  2. Add an entry to the correct category list below.
  3. Assign a scoring function.
  4. Update sources/barchart.py scraper to extract the new field.
"""

from config.indicators_tradingview import (
    ma_vs_price,
    rsi_signal,
    stoch_signal,
    williams_signal,
    threshold_signal,
    zero_cross_signal,
    macd_crossover,
    adx_signal,
    no_signal,
    SCORE_FUNCTIONS,
    get_score_fn,
)

# ---------------------------------------------------------------------------
# BarChart Opinion (primary BC signal — Signal #2)
# ---------------------------------------------------------------------------

OPINION = [
    {"key": "BC_OPINION_SHORT",     "bc_field": "opinion_short",     "description": "BC Short-Term Opinion",  "score_fn": "bc_opinion_signal", "params": {}},
    {"key": "BC_OPINION_MEDIUM",    "bc_field": "opinion_medium",    "description": "BC Medium-Term Opinion", "score_fn": "bc_opinion_signal", "params": {}},
    {"key": "BC_OPINION_LONG",      "bc_field": "opinion_long",      "description": "BC Long-Term Opinion",   "score_fn": "bc_opinion_signal", "params": {}},
    {"key": "BC_OPINION_OVERALL",   "bc_field": "opinion_overall",   "description": "BC Overall Opinion",     "score_fn": "bc_opinion_signal", "params": {}},
    {"key": "BC_SIGNAL_STRENGTH",   "bc_field": "signal_strength",   "description": "BC Signal Strength",     "score_fn": "none",              "params": {}},
    {"key": "BC_SIGNAL_DIRECTION",  "bc_field": "signal_direction",  "description": "BC Signal Direction",    "score_fn": "none",              "params": {}},
]

# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

MOVING_AVERAGES = [
    {"key": "BC_SMA_20",  "bc_field": "ma20",   "description": "BC SMA 20",  "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_SMA_50",  "bc_field": "ma50",   "description": "BC SMA 50",  "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_SMA_100", "bc_field": "ma100",  "description": "BC SMA 100", "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_SMA_200", "bc_field": "ma200",  "description": "BC SMA 200", "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_EMA_20",  "bc_field": "ema20",  "description": "BC EMA 20",  "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_EMA_50",  "bc_field": "ema50",  "description": "BC EMA 50",  "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_EMA_100", "bc_field": "ema100", "description": "BC EMA 100", "score_fn": "ma_vs_price", "params": {}},
    {"key": "BC_EMA_200", "bc_field": "ema200", "description": "BC EMA 200", "score_fn": "ma_vs_price", "params": {}},
]

# ---------------------------------------------------------------------------
# Oscillators
# ---------------------------------------------------------------------------

OSCILLATORS = [
    {
        "key": "BC_RSI_14", "bc_field": "rsi14", "description": "BC RSI 14",
        "score_fn": "rsi_signal",
        "params": {"buy": 55, "sell": 45, "overbought": 70, "oversold": 30},
    },
    {
        "key": "BC_STOCH_K", "bc_field": "stochasticK", "description": "BC Stochastic %K",
        "score_fn": "stoch_signal",
        "params": {"overbought": 80, "oversold": 20},
    },
    {
        "key": "BC_STOCH_D", "bc_field": "stochasticD", "description": "BC Stochastic %D",
        "score_fn": "stoch_signal",
        "params": {"overbought": 80, "oversold": 20},
    },
    {
        "key": "BC_WILLIAMS_R", "bc_field": "williamsPercentR", "description": "BC Williams %R",
        "score_fn": "williams_signal",
        "params": {"overbought": -20, "oversold": -80},
    },
    {
        "key": "BC_CCI_20", "bc_field": "cci", "description": "BC CCI 20",
        "score_fn": "threshold_signal",
        "params": {"buy": 100, "sell": -100},
    },
    {
        "key": "BC_MOMENTUM", "bc_field": "momentum", "description": "BC Momentum",
        "score_fn": "zero_cross_signal",
        "params": {},
    },
]

# ---------------------------------------------------------------------------
# Trend indicators
# ---------------------------------------------------------------------------

TREND = [
    {"key": "BC_MACD_LINE",        "bc_field": "macd",          "description": "BC MACD Line",        "score_fn": "none",            "params": {}},
    {"key": "BC_MACD_SIGNAL_LINE", "bc_field": "macdSignal",    "description": "BC MACD Signal Line",  "score_fn": "none",            "params": {}},
    {"key": "BC_MACD_CROSSOVER",   "bc_field": "macd",          "description": "BC MACD Crossover",    "score_fn": "macd_crossover",  "params": {"signal_key": "macdSignal"}},
    {"key": "BC_MACD_HISTOGRAM",   "bc_field": "macdHistogram", "description": "BC MACD Histogram",    "score_fn": "zero_cross_signal","params": {}},
    {
        "key": "BC_ADX", "bc_field": "adx", "description": "BC ADX",
        "score_fn": "adx_signal",
        "params": {"plus_key": "adxPlusDI", "minus_key": "adxMinusDI", "trend_threshold": 25},
    },
    {"key": "BC_ADX_PLUS_DI",  "bc_field": "adxPlusDI",  "description": "BC ADX +DI", "score_fn": "none", "params": {}},
    {"key": "BC_ADX_MINUS_DI", "bc_field": "adxMinusDI", "description": "BC ADX -DI", "score_fn": "none", "params": {}},
]

# ---------------------------------------------------------------------------
# Price & volume context (logged, not scored)
# ---------------------------------------------------------------------------

PRICE_VOLUME = [
    {"key": "BC_CLOSE",      "bc_field": "lastPrice",        "description": "BC Last Price",   "score_fn": "none", "params": {}},
    {"key": "BC_OPEN",       "bc_field": "open",             "description": "BC Open",         "score_fn": "none", "params": {}},
    {"key": "BC_HIGH",       "bc_field": "high",             "description": "BC High",         "score_fn": "none", "params": {}},
    {"key": "BC_LOW",        "bc_field": "low",              "description": "BC Low",          "score_fn": "none", "params": {}},
    {"key": "BC_VOLUME",     "bc_field": "volume",           "description": "BC Volume",       "score_fn": "none", "params": {}},
    {"key": "BC_AVG_VOLUME", "bc_field": "avgVolume",        "description": "BC Avg Volume",   "score_fn": "none", "params": {}},
    {"key": "BC_52W_HIGH",   "bc_field": "fiftyTwoWeekHigh", "description": "BC 52-Week High", "score_fn": "none", "params": {}},
    {"key": "BC_52W_LOW",    "bc_field": "fiftyTwoWeekLow",  "description": "BC 52-Week Low",  "score_fn": "none", "params": {}},
    {"key": "BC_PCT_CHANGE", "bc_field": "percentChange",    "description": "BC % Change",     "score_fn": "none", "params": {}},
]

# ---------------------------------------------------------------------------
# TrendSpotter fields (feed Signal #3 — TrendSpotterSignal model)
# ---------------------------------------------------------------------------

TRENDSPOTTER = [
    {"key": "TS_SIGNAL",         "bc_field": "trendspotter",          "description": "TrendSpotter Signal",      "score_fn": "trendspotter_signal", "params": {}},
    {"key": "TS_STRENGTH",       "bc_field": "trendspotter_strength", "description": "TrendSpotter Strength",    "score_fn": "none",                "params": {}},
    {"key": "TS_CHANGE",         "bc_field": "trendspotter_change",   "description": "TrendSpotter Change",      "score_fn": "none",                "params": {}},
    {"key": "TS_DATE",           "bc_field": "trendspotter_date",     "description": "TrendSpotter Signal Date", "score_fn": "none",                "params": {}},
    {"key": "TS_DAYS_IN_SIGNAL", "bc_field": "days_in_signal",        "description": "Days at TS Signal",       "score_fn": "none",                "params": {}},
]

# ---------------------------------------------------------------------------
# BarChart-specific scoring functions
# ---------------------------------------------------------------------------

_BC_OPINION_MAP = {
    "strong buy":  "BUY",
    "buy":         "BUY",
    "hold":        "HOLD",
    "sell":        "SELL",
    "strong sell": "SELL",
}

def bc_opinion_signal(value, indicators: dict, params: dict) -> str:
    if value is None:
        return "N/A"
    return _BC_OPINION_MAP.get(str(value).lower().strip(), "NEUTRAL")


_TS_SIGNAL_MAP = {
    "buy":  "BUY",
    "sell": "SELL",
    "hold": "HOLD",
}

def trendspotter_signal(value, indicators: dict, params: dict) -> str:
    if value is None:
        return "N/A"
    return _TS_SIGNAL_MAP.get(str(value).lower().strip(), "HOLD")


# Register BC-specific functions into the shared dispatch table
SCORE_FUNCTIONS["bc_opinion_signal"]   = bc_opinion_signal
SCORE_FUNCTIONS["trendspotter_signal"] = trendspotter_signal

# ---------------------------------------------------------------------------
# All categories — used by the scraper to iterate
# ---------------------------------------------------------------------------

ALL_CATEGORIES = {
    "opinion":         OPINION,
    "moving_averages": MOVING_AVERAGES,
    "oscillators":     OSCILLATORS,
    "trend":           TREND,
    "price_volume":    PRICE_VOLUME,
    "trendspotter":    TRENDSPOTTER,
}
