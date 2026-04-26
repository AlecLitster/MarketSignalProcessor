"""
config/indicators_tradingview.py
---------------------------------
Registry of every TradingView indicator processed by this system,
plus all shared scoring functions used by both TV and BarChart adapters.

To add a new indicator:
  1. Find the field name from tradingview_ta's analysis.indicators dict.
  2. Add an entry to the correct category list below.
  3. Assign a scoring function from SCORE_FUNCTIONS (or add a new one).
  4. No changes needed in sources/tradingview.py.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Scoring functions
# Each function signature: (value, indicators: dict, params: dict) -> str
# Returns one of: BUY | SELL | NEUTRAL | OVERBOUGHT | OVERSOLD | WEAK_TREND | N/A
# ---------------------------------------------------------------------------

def ma_vs_price(value: Optional[float], indicators: dict, params: dict) -> str:
    """BUY if price > MA, SELL if price < MA."""
    price = indicators.get("close")
    if value is None or price is None:
        return "N/A"
    if price > value:
        return "BUY"
    if price < value:
        return "SELL"
    return "NEUTRAL"


def rsi_signal(value: Optional[float], indicators: dict, params: dict) -> str:
    if value is None:
        return "N/A"
    overbought = params.get("overbought", 70)
    oversold   = params.get("oversold",   30)
    buy        = params.get("buy",        55)
    sell       = params.get("sell",       45)
    if value >= overbought:
        return "OVERBOUGHT"
    if value <= oversold:
        return "OVERSOLD"
    if value >= buy:
        return "BUY"
    if value <= sell:
        return "SELL"
    return "NEUTRAL"


def stoch_signal(value: Optional[float], indicators: dict, params: dict) -> str:
    if value is None:
        return "N/A"
    overbought = params.get("overbought", 80)
    oversold   = params.get("oversold",   20)
    if value >= overbought:
        return "OVERBOUGHT"
    if value <= oversold:
        return "OVERSOLD"
    return "NEUTRAL"


def williams_signal(value: Optional[float], indicators: dict, params: dict) -> str:
    if value is None:
        return "N/A"
    overbought = params.get("overbought", -20)
    oversold   = params.get("oversold",   -80)
    if value >= overbought:
        return "OVERBOUGHT"
    if value <= oversold:
        return "OVERSOLD"
    return "NEUTRAL"


def threshold_signal(value: Optional[float], indicators: dict, params: dict) -> str:
    """BUY above buy threshold, SELL below sell threshold."""
    if value is None:
        return "N/A"
    buy  = params.get("buy",   100)
    sell = params.get("sell", -100)
    if value > buy:
        return "BUY"
    if value < sell:
        return "SELL"
    return "NEUTRAL"


def zero_cross_signal(value: Optional[float], indicators: dict, params: dict) -> str:
    """BUY if value > 0, SELL if value < 0."""
    if value is None:
        return "N/A"
    if value > 0:
        return "BUY"
    if value < 0:
        return "SELL"
    return "NEUTRAL"


def macd_crossover(value: Optional[float], indicators: dict, params: dict) -> str:
    """BUY if MACD line > signal line, SELL if below."""
    if value is None:
        return "N/A"
    signal_key = params.get("signal_key", "MACD.signal")
    sig_val    = indicators.get(signal_key)
    if sig_val is None:
        return "N/A"
    if value > sig_val:
        return "BUY"
    if value < sig_val:
        return "SELL"
    return "NEUTRAL"


def adx_signal(value: Optional[float], indicators: dict, params: dict) -> str:
    """WEAK_TREND if ADX < threshold; else BUY/SELL based on +DI/-DI."""
    if value is None:
        return "N/A"
    threshold = params.get("trend_threshold", 25)
    if value < threshold:
        return "WEAK_TREND"
    plus_key  = params.get("plus_key",  "ADX+DI")
    minus_key = params.get("minus_key", "ADX-DI")
    plus  = indicators.get(plus_key)
    minus = indicators.get(minus_key)
    if plus is None or minus is None:
        return "NEUTRAL"
    if plus > minus:
        return "BUY"
    if minus > plus:
        return "SELL"
    return "NEUTRAL"


def no_signal(value: Any, indicators: dict, params: dict) -> str:
    return "N/A"


# ---------------------------------------------------------------------------
# Dispatch table — shared with indicators_barchart.py
# ---------------------------------------------------------------------------

SCORE_FUNCTIONS: dict[str, Callable] = {
    "ma_vs_price":      ma_vs_price,
    "rsi_signal":       rsi_signal,
    "stoch_signal":     stoch_signal,
    "williams_signal":  williams_signal,
    "threshold_signal": threshold_signal,
    "zero_cross_signal":zero_cross_signal,
    "macd_crossover":   macd_crossover,
    "adx_signal":       adx_signal,
    "none":             no_signal,
}


def get_score_fn(name: str) -> Callable:
    return SCORE_FUNCTIONS.get(name, no_signal)


# ---------------------------------------------------------------------------
# Moving Averages
# tv_key: field name in tradingview_ta analysis.indicators
# ---------------------------------------------------------------------------

MOVING_AVERAGES: list[dict] = [
    {"key": "TV_SMA5",   "tv_key": "SMA5",      "description": "SMA 5",      "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_SMA10",  "tv_key": "SMA10",     "description": "SMA 10",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_SMA20",  "tv_key": "SMA20",     "description": "SMA 20",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_SMA30",  "tv_key": "SMA30",     "description": "SMA 30",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_SMA50",  "tv_key": "SMA50",     "description": "SMA 50",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_SMA100", "tv_key": "SMA100",    "description": "SMA 100",    "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_SMA200", "tv_key": "SMA200",    "description": "SMA 200",    "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA5",   "tv_key": "EMA5",      "description": "EMA 5",      "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA10",  "tv_key": "EMA10",     "description": "EMA 10",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA20",  "tv_key": "EMA20",     "description": "EMA 20",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA30",  "tv_key": "EMA30",     "description": "EMA 30",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA50",  "tv_key": "EMA50",     "description": "EMA 50",     "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA100", "tv_key": "EMA100",    "description": "EMA 100",    "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_EMA200", "tv_key": "EMA200",    "description": "EMA 200",    "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_VWMA",   "tv_key": "VWMA",      "description": "VWMA",       "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_HULL9",  "tv_key": "Hull_MA_9", "description": "Hull MA 9",  "score_fn": "ma_vs_price", "params": {}},
    {"key": "TV_ICHI_B", "tv_key": "Ichimoku.BLine", "description": "Ichimoku Base", "score_fn": "ma_vs_price", "params": {}},
]

# ---------------------------------------------------------------------------
# Oscillators
# ---------------------------------------------------------------------------

OSCILLATORS: list[dict] = [
    {
        "key": "TV_RSI", "tv_key": "RSI", "description": "RSI 14",
        "score_fn": "rsi_signal",
        "params": {"buy": 55, "sell": 45, "overbought": 70, "oversold": 30},
    },
    {
        "key": "TV_STOCH_K", "tv_key": "Stoch.K", "description": "Stochastic %K",
        "score_fn": "stoch_signal",
        "params": {"overbought": 80, "oversold": 20},
    },
    {
        "key": "TV_STOCH_D", "tv_key": "Stoch.D", "description": "Stochastic %D",
        "score_fn": "stoch_signal",
        "params": {"overbought": 80, "oversold": 20},
    },
    {
        "key": "TV_CCI20", "tv_key": "CCI20", "description": "CCI 20",
        "score_fn": "threshold_signal",
        "params": {"buy": 100, "sell": -100},
    },
    {
        "key": "TV_AO", "tv_key": "AO", "description": "Awesome Oscillator",
        "score_fn": "zero_cross_signal",
        "params": {},
    },
    {
        "key": "TV_MOMENTUM", "tv_key": "Mom", "description": "Momentum 10",
        "score_fn": "zero_cross_signal",
        "params": {},
    },
    {
        "key": "TV_WILLIAMS", "tv_key": "W.R", "description": "Williams %R",
        "score_fn": "williams_signal",
        "params": {"overbought": -20, "oversold": -80},
    },
    {
        "key": "TV_BBP", "tv_key": "BBPower", "description": "Bull Bear Power",
        "score_fn": "zero_cross_signal",
        "params": {},
    },
    {
        "key": "TV_UO", "tv_key": "UO", "description": "Ultimate Oscillator",
        "score_fn": "rsi_signal",
        "params": {"buy": 55, "sell": 45, "overbought": 70, "oversold": 30},
    },
]

# ---------------------------------------------------------------------------
# Trend indicators
# ---------------------------------------------------------------------------

TREND: list[dict] = [
    {"key": "TV_MACD_LINE",   "tv_key": "MACD.macd",   "description": "MACD Line",     "score_fn": "none",          "params": {}},
    {"key": "TV_MACD_SIGNAL", "tv_key": "MACD.signal", "description": "MACD Signal",   "score_fn": "none",          "params": {}},
    {
        "key": "TV_MACD_CROSS", "tv_key": "MACD.macd", "description": "MACD Crossover",
        "score_fn": "macd_crossover",
        "params": {"signal_key": "MACD.signal"},
    },
    {
        "key": "TV_ADX", "tv_key": "ADX", "description": "ADX",
        "score_fn": "adx_signal",
        "params": {"plus_key": "ADX+DI", "minus_key": "ADX-DI", "trend_threshold": 25},
    },
    {"key": "TV_ADX_PLUS",  "tv_key": "ADX+DI", "description": "ADX +DI", "score_fn": "none", "params": {}},
    {"key": "TV_ADX_MINUS", "tv_key": "ADX-DI", "description": "ADX -DI", "score_fn": "none", "params": {}},
]

# ---------------------------------------------------------------------------
# Volume (logged, not scored)
# ---------------------------------------------------------------------------

VOLUME: list[dict] = [
    {"key": "TV_VOLUME", "tv_key": "volume", "description": "Volume", "score_fn": "none", "params": {}},
    {"key": "TV_VWMA_V", "tv_key": "VWMA",   "description": "VWMA",   "score_fn": "none", "params": {}},
]

# ---------------------------------------------------------------------------
# Pivot point configuration
# ---------------------------------------------------------------------------

PIVOT_TYPES:  list[str] = ["Classic", "Fibonacci", "Camarilla", "Woodie", "Demark"]
PIVOT_LEVELS: list[str] = ["Middle", "S1", "S2", "S3", "R1", "R2", "R3"]

PIVOT_DISPLAY: dict[str, str] = {
    "Middle": "PP",
    "S1": "S1", "S2": "S2", "S3": "S3",
    "R1": "R1", "R2": "R2", "R3": "R3",
}


def pivot_tv_key(pivot_type: str, level: str) -> str:
    """Build the tradingview_ta key for a pivot point e.g. 'Pivot.M.Classic.R1'."""
    return f"Pivot.M.{pivot_type}.{level}"


# ---------------------------------------------------------------------------
# Summary field names (from analysis.summary)
# ---------------------------------------------------------------------------

SUMMARY_FIELDS: list[str] = ["BUY", "SELL", "NEUTRAL", "RECOMMENDATION"]
