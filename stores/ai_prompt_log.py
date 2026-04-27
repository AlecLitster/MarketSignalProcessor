"""
stores/ai_prompt_log.py
-----------------------
Per-cycle AI analysis prompt log.

Overwrites logs/ai_prompt.txt on every cycle with a ready-to-paste LLM prompt
containing raw technical indicator values.  All buy/sell/hold labels, computed
scores, consensus fields, AI results, and swing events are stripped — the AI
must derive every conclusion from the raw numbers alone.

Usage: copy the file contents into any capable LLM to receive an unbiased
       technical analysis and formatted professional dashboard.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from config.settings import LOG_AI_PROMPT_ENABLED, LOG_AI_PROMPT_FILE, LOG_DIR
from core.models import CycleResult, SourceSignal

log = logging.getLogger(__name__)

# ── Indicator categories that contain string-based signal labels, not numbers ──
_SKIP_CATS = frozenset({"opinion"})

# ── TV indicator categories too noisy to include in an AI prompt ──────────────
_TV_SKIP_CATS = frozenset({"pivots", "opinion"})

# ── Source prefix strips for cleaner key names ────────────────────────────────
_KEY_PREFIXES = ("BC_", "TV_", "YF_")

# ── TV raw-dict keys to include for the weekly timeframe summary ──────────────
_TV_WEEKLY_MAP: dict[str, str] = {
    "close":       "close",
    "RSI":         "RSI",
    "MACD.macd":   "MACD",
    "MACD.signal": "MACD_SIG",
    "MACD.hist":   "MACD_HIST",
    "SMA20":       "SMA20",
    "SMA50":       "SMA50",
    "SMA200":      "SMA200",
    "ADX":         "ADX",
    "ADX+DI":      "ADX+DI",
    "ADX-DI":      "ADX-DI",
}


# ── Value formatter ───────────────────────────────────────────────────────────

def _fv(val) -> Optional[str]:
    if val is None:
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    a = abs(n)
    if a >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if a >= 10_000:
        return f"{n / 1_000:.1f}K"
    if a >= 100:
        return f"{n:.1f}"
    return f"{n:.3f}"


# ── Indicator formatters ──────────────────────────────────────────────────────

def _strip_prefix(key: str) -> str:
    for pfx in _KEY_PREFIXES:
        if key.startswith(pfx):
            return key[len(pfx):]
    return key


def _iv_pairs(ivs: list) -> list[str]:
    """Return key=value strings for IndicatorValues that have a numeric value."""
    pairs = []
    for iv in ivs:
        v = _fv(iv.value)
        if v is not None:
            pairs.append(f"{_strip_prefix(iv.key)}={v}")
    return pairs


def _format_source_lines(label: str, src: SourceSignal, skip_cats: frozenset) -> list[str]:
    """One line per indicator category, skipping signal-only categories."""
    lines = []
    for cat, ivs in src.indicators.items():
        if cat in skip_cats:
            continue
        pairs = _iv_pairs(ivs)
        if pairs:
            lines.append(f"  {label}:{cat[:4]:<8}  {' '.join(pairs)}")
    return lines


def _format_tv_weekly(raw_weekly: dict) -> Optional[str]:
    if not raw_weekly:
        return None
    pairs = []
    for tv_key, label in _TV_WEEKLY_MAP.items():
        v = _fv(raw_weekly.get(tv_key))
        if v is not None:
            pairs.append(f"{label}={v}")
    return f"  tv:weekly    {' '.join(pairs)}" if pairs else None


# ── Prompt template ───────────────────────────────────────────────────────────

_DIVIDER  = "═" * 79
_SEP      = "─" * 79

_INTRO = """\
{divider}
  MARKET TECHNICAL ANALYSIS   {ts}
{divider}

INSTRUCTIONS
{sep}
You are a professional quantitative financial analyst. The dataset below contains
raw technical indicator values captured in a single polling cycle. No buy/sell/hold
recommendations, computed scores, or prior AI conclusions are included — derive
every signal entirely from the raw numerical values provided.

Produce the following output:

  1. PER-TICKER SIGNAL ANALYSIS
     For each security provide:
       Signal      BUY | SELL | HOLD
       Confidence  HIGH | MEDIUM | LOW
       Factors     3–5 concise bullet points citing specific indicator values
                   and what they imply (e.g. "RSI=72 → approaching overbought")

  2. MARKET REGIME ASSESSMENT
     Classify the current regime: Risk-On / Risk-Off / Neutral
     Support with 2–3 sentences covering cross-ticker momentum, breadth,
     trend alignment, and any notable divergences.

  3. PROFESSIONAL SUMMARY DASHBOARD
     Return a clean formatted table:

     Ticker   | Signal | Conf.  | Price    | Key Factor
     ---------|--------|--------|----------|----------------------------
     (fill)   |        |        |          |

DATA
{sep}
Sources  : {sources}
Captured : {ts}
Tickers  : {tickers}
{sep}"""


# ── Public API ────────────────────────────────────────────────────────────────

def write(results: list[CycleResult]) -> None:
    """Write the AI prompt log, overwriting the previous cycle's file."""
    if not LOG_AI_PROMPT_ENABLED or not results:
        return

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Collect which sources are active (deduplicated, preserving order)
    seen: dict[str, None] = {}
    for r in results:
        if r.tradingview: seen["TradingView"] = None
        if r.yfinance:    seen["YFinance"]    = None
    sources = " · ".join(seen)
    tickers = " · ".join(r.ticker for r in results)

    blocks: list[str] = [
        _INTRO.format(
            divider=_DIVIDER, sep=_SEP,
            ts=ts, sources=sources, tickers=tickers,
        )
    ]

    for result in results:
        price_str = f"${result.price:.2f}" if result.price is not None else "N/A"
        blocks.append(
            f"\n▌ {result.ticker:<6}  {price_str:<10}  {result.timestamp.strftime('%H:%M:%S')}"
        )

        # TradingView — daily indicators + key weekly values
        if result.tradingview:
            blocks.extend(
                _format_source_lines("tv:daily", result.tradingview, _TV_SKIP_CATS)
            )
            weekly_line = _format_tv_weekly(
                result.tradingview.raw.get("weekly", {})
            )
            if weekly_line:
                blocks.append(weekly_line)

        # YFinance
        if result.yfinance:
            blocks.extend(
                _format_source_lines("yf", result.yfinance, _SKIP_CATS)
            )

        blocks.append(_SEP)

    content = "\n".join(blocks) + "\n"

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_AI_PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        log.info("AI prompt log → %s", LOG_AI_PROMPT_FILE)
    except IOError as exc:
        log.error("AI prompt log write failed: %s", exc)
