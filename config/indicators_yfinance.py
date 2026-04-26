"""
config/indicators_yfinance.py
------------------------------
Indicator registry and scoring functions for the yfinance + pandas_ta source.

Each entry in INDICATORS drives one pandas_ta computation and maps the result
to a BUY / SELL / HOLD label via the named scoring function.

Score mapping used by the aggregator:
  BUY  → +1.0   HOLD → 0.0   SELL → -1.0

Weighted average of all indicator scores → overall source score [-1, +1].
"""

from __future__ import annotations

from typing import Optional
import pandas as pd


# ---------------------------------------------------------------------------
# Indicator registry
# ---------------------------------------------------------------------------

INDICATORS: list[dict] = [
    # Moving averages
    {"key": "SMA_20",  "fn": "sma",    "params": {"length": 20},  "score": "price_vs_ma",  "weight": 1.0},
    {"key": "SMA_50",  "fn": "sma",    "params": {"length": 50},  "score": "price_vs_ma",  "weight": 1.5},
    {"key": "SMA_200", "fn": "sma",    "params": {"length": 200}, "score": "price_vs_ma",  "weight": 2.0},
    {"key": "EMA_9",   "fn": "ema",    "params": {"length": 9},   "score": "price_vs_ma",  "weight": 0.5},
    {"key": "EMA_21",  "fn": "ema",    "params": {"length": 21},  "score": "price_vs_ma",  "weight": 1.0},
    # Oscillators
    {"key": "RSI_14",  "fn": "rsi",    "params": {"length": 14},  "score": "rsi",          "weight": 1.5},
    {"key": "MACD",    "fn": "macd",   "params": {"fast": 12, "slow": 26, "signal": 9},
                                                                   "score": "macd",         "weight": 1.5},
    {"key": "STOCH",   "fn": "stoch",  "params": {"k": 14, "d": 3, "smooth_k": 3},
                                                                   "score": "stoch",        "weight": 1.0},
    # Trend
    {"key": "ADX_14",  "fn": "adx",    "params": {"length": 14},  "score": "adx",          "weight": 1.0},
    {"key": "BBANDS",  "fn": "bbands", "params": {"length": 20, "std": 2.0},
                                                                   "score": "bbands",       "weight": 1.0},
    # Volume
    {"key": "OBV",     "fn": "obv",    "params": {},               "score": "obv",          "weight": 0.5},
]

# Organise indicator keys into display categories
CATEGORIES: dict[str, list[str]] = {
    "moving_averages": ["SMA_20", "SMA_50", "SMA_200", "EMA_9", "EMA_21"],
    "oscillators":     ["RSI_14", "MACD", "STOCH"],
    "trend":           ["ADX_14", "BBANDS"],
    "volume":          ["OBV"],
}

INDICATOR_WEIGHTS: dict[str, float] = {ind["key"]: ind["weight"] for ind in INDICATORS}

# RSI thresholds
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD   = 30.0

# Stochastic thresholds
STOCH_OVERBOUGHT = 80.0
STOCH_OVERSOLD   = 20.0

# ADX trend-strength threshold
ADX_TREND_THRESHOLD = 25.0


# ---------------------------------------------------------------------------
# pandas_ta column name helpers
# ---------------------------------------------------------------------------

def col_sma(length: int) -> str:
    return f"SMA_{length}"

def col_ema(length: int) -> str:
    return f"EMA_{length}"

def col_rsi(length: int) -> str:
    return f"RSI_{length}"

def col_macd(fast: int, slow: int, signal: int) -> tuple[str, str, str]:
    """Returns (macd_line, signal_line, histogram) column names."""
    return f"MACD_{fast}_{slow}_{signal}", f"MACDs_{fast}_{slow}_{signal}", f"MACDh_{fast}_{slow}_{signal}"

def col_stoch(k: int, d: int, smooth_k: int) -> tuple[str, str]:
    """Returns (%K, %D) column names."""
    return f"STOCHk_{k}_{d}_{smooth_k}", f"STOCHd_{k}_{d}_{smooth_k}"

def col_adx(length: int) -> tuple[str, str, str]:
    """Returns (adx, DI+, DI-) column names."""
    return f"ADX_{length}", f"DMP_{length}", f"DMN_{length}"

def col_bbands(length: int, std: float) -> tuple[str, str, str]:
    """Returns (lower, middle, upper) column name prefixes.
    Exact suffix varies by pandas_ta version; use startswith() matching in practice.
    """
    std_str = f"{std:.1f}"
    return f"BBL_{length}_{std_str}", f"BBM_{length}_{std_str}", f"BBU_{length}_{std_str}"


# ---------------------------------------------------------------------------
# Scoring functions — all return "BUY" | "SELL" | "HOLD" | "N/A"
# ---------------------------------------------------------------------------

def score_price_vs_ma(price: Optional[float], ma: Optional[float]) -> str:
    if price is None or ma is None or pd.isna(ma):
        return "N/A"
    if price > ma:
        return "BUY"
    if price < ma:
        return "SELL"
    return "HOLD"


def score_rsi(rsi: Optional[float]) -> str:
    if rsi is None or pd.isna(rsi):
        return "N/A"
    if rsi <= RSI_OVERSOLD:
        return "BUY"
    if rsi >= RSI_OVERBOUGHT:
        return "SELL"
    return "HOLD"


def score_macd(macd_line: Optional[float], signal_line: Optional[float]) -> str:
    if macd_line is None or signal_line is None or pd.isna(macd_line) or pd.isna(signal_line):
        return "N/A"
    if macd_line > signal_line:
        return "BUY"
    if macd_line < signal_line:
        return "SELL"
    return "HOLD"


def score_stoch(k: Optional[float]) -> str:
    if k is None or pd.isna(k):
        return "N/A"
    if k <= STOCH_OVERSOLD:
        return "BUY"
    if k >= STOCH_OVERBOUGHT:
        return "SELL"
    return "HOLD"


def score_adx(adx: Optional[float], dmp: Optional[float], dmn: Optional[float]) -> str:
    """ADX gives direction only when trend is strong (ADX > threshold)."""
    if adx is None or dmp is None or dmn is None:
        return "N/A"
    if pd.isna(adx) or pd.isna(dmp) or pd.isna(dmn):
        return "N/A"
    if adx < ADX_TREND_THRESHOLD:
        return "HOLD"   # weak trend — no directional conviction
    return "BUY" if dmp > dmn else "SELL"


def score_bbands(price: Optional[float], lower: Optional[float], upper: Optional[float]) -> str:
    if price is None or lower is None or upper is None:
        return "N/A"
    if pd.isna(lower) or pd.isna(upper):
        return "N/A"
    if price < lower:
        return "BUY"    # oversold below lower band
    if price > upper:
        return "SELL"   # overbought above upper band
    return "HOLD"


def score_obv(obv_series: Optional["pd.Series"]) -> str:
    """OBV trend: compare current to 10-period moving average."""
    if obv_series is None or len(obv_series) < 11:
        return "N/A"
    current = obv_series.iloc[-1]
    avg     = obv_series.iloc[-11:-1].mean()
    if pd.isna(current) or pd.isna(avg):
        return "N/A"
    if current > avg:
        return "BUY"
    if current < avg:
        return "SELL"
    return "HOLD"


# ---------------------------------------------------------------------------
# Signal → numeric score
# ---------------------------------------------------------------------------

SIGNAL_SCORE: dict[str, float] = {
    "BUY":  +1.0,
    "HOLD":  0.0,
    "SELL": -1.0,
    "N/A":   0.0,
}


def signal_to_score(signal: str) -> float:
    return SIGNAL_SCORE.get(signal, 0.0)
