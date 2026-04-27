"""
core/swing.py
-------------
Detects significant changes in signal or score between polling cycles.

Compares each ticker's current consensus score against the rolling average
of the last SWING_HISTORY_WINDOW cycles from the per-ticker history store.

Swing labels (mutually exclusive, assigned in priority order):
  STRONG_SWING  — |delta| >= SWING_SCORE_STRONG_DELTA_THRESHOLD (0.50)
  WEAK_SWING    — |delta| >= SWING_SCORE_WEAK_DELTA_THRESHOLD   (0.35)
  SCORE_SWING   — |delta| >= SWING_SCORE_DELTA_THRESHOLD        (0.25)
  SIGNAL_CHANGE — BUY/SELL/HOLD label flipped, delta below all thresholds
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config.settings import (
    SWING_HISTORY_WINDOW,
    SWING_MIN_HISTORY_ENTRIES,
    SWING_SCORE_DELTA_THRESHOLD,
    SWING_SCORE_WEAK_DELTA_THRESHOLD,
    SWING_SCORE_STRONG_DELTA_THRESHOLD,
)
from core.models import CycleResult, SwingEvent

log = logging.getLogger(__name__)


def _classify_swing(
    delta: float,
    signal_changed: bool,
) -> Optional[str]:
    """Return the swing label or None if no swing threshold is met."""
    abs_delta = abs(delta)
    if abs_delta >= SWING_SCORE_STRONG_DELTA_THRESHOLD:
        return "STRONG_SWING"
    if abs_delta >= SWING_SCORE_WEAK_DELTA_THRESHOLD:
        return "WEAK_SWING"
    if abs_delta >= SWING_SCORE_DELTA_THRESHOLD:
        return "SCORE_SWING"
    if signal_changed:
        return "SIGNAL_CHANGE"
    return None


def detect_swing(
    result: CycleResult,
    history: list[dict],
) -> Optional[SwingEvent]:
    """
    Compare result against history and return a SwingEvent if warranted.

    Args:
        result:  the freshly computed CycleResult for this cycle.
        history: list of past CycleResult.as_dict() entries for this ticker,
                 ordered oldest → newest, from the ticker JSON store.
    Returns:
        SwingEvent if a significant change is detected, else None.
    """
    if len(history) < SWING_MIN_HISTORY_ENTRIES:
        return None

    recent = history[-SWING_HISTORY_WINDOW:]

    scores  = [e.get("consensus_score", 0.0) for e in recent]
    signals = [e.get("consensus_signal", "HOLD") for e in recent]

    avg_score        = sum(scores) / len(scores)
    current_score    = result.consensus_score
    current_signal   = result.consensus_signal
    previous_signal  = signals[-1] if signals else "HOLD"
    delta            = current_score - avg_score
    signal_changed   = current_signal != previous_signal

    label = _classify_swing(delta, signal_changed)
    if label is None:
        return None

    # Determine which sources contributed to the change
    sources_changed = []
    if result.tradingview and len(recent) > 0:
        prev_tv = recent[-1].get("tradingview")
        if prev_tv and prev_tv.get("signal") != result.tradingview.signal:
            sources_changed.append("tradingview")
    event = SwingEvent(
        ticker          = result.ticker,
        timestamp       = result.timestamp,
        previous_signal = previous_signal,
        current_signal  = current_signal,
        previous_score  = round(avg_score, 4),
        current_score   = current_score,
        score_delta     = round(delta, 4),
        label           = label,
        sources_changed = sources_changed,
    )

    log.info(
        "SWING [%s] %s: %s → %s  delta=%+.4f  sources=%s",
        label,
        result.ticker,
        previous_signal,
        current_signal,
        delta,
        sources_changed or "none",
    )

    return event


def detect_swings(
    results: list[CycleResult],
    history_map: dict[str, list[dict]],
) -> list[CycleResult]:
    """
    Detect swings for all tickers and write SwingEvent into each CycleResult.

    Args:
        results:     list of CycleResults from this cycle.
        history_map: {ticker: [past CycleResult dicts]} from ticker store.
    Returns:
        Same results list with swing_event populated where warranted.
    """
    for result in results:
        history = history_map.get(result.ticker, [])
        swing   = detect_swing(result, history)
        result.swing_event = swing
    return results
