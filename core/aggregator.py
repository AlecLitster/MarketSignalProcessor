"""
core/aggregator.py
------------------
Computes the consensus signal across all active sources for each ticker.

The consensus is a weighted average of:
  - TradingView score  (weight: CONSENSUS_WEIGHTS["tradingview"])
  - YFinance score     (weight: CONSENSUS_WEIGHTS["yfinance"])

If a source is unavailable (None), its weight is redistributed
proportionally across the remaining active sources so the consensus
score always represents the full 0.0–1.0 range.
"""

from __future__ import annotations

import logging

from config.settings import (
    CONSENSUS_WEIGHTS,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
)
from core.models import CycleResult

log = logging.getLogger(__name__)


def _redistribute_weights(weights: dict[str, float], active_keys: set[str]) -> dict[str, float]:
    """Redistribute weights of missing sources proportionally across active ones."""
    active_weights = {k: v for k, v in weights.items() if k in active_keys}
    total = sum(active_weights.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in active_weights.items()}


def compute_consensus(result: CycleResult) -> tuple[str, float]:
    """
    Compute consensus signal and score for a CycleResult.

    Returns (signal, score) where signal is BUY | SELL | HOLD
    and score is in range -1.0 → +1.0.
    """
    available: dict[str, float] = {}

    if result.tradingview is not None:
        available["tradingview"] = result.tradingview.score
    if result.yfinance is not None:
        available["yfinance"] = result.yfinance.score

    if not available:
        log.warning("%s: no source data — consensus defaulting to HOLD", result.ticker)
        return "HOLD", 0.0

    weights = _redistribute_weights(CONSENSUS_WEIGHTS, set(available.keys()))
    score   = sum(available[src] * weights[src] for src in available)
    score   = round(score, 4)

    if score >= BUY_THRESHOLD:
        signal = "BUY"
    elif score <= SELL_THRESHOLD:
        signal = "SELL"
    else:
        signal = "HOLD"

    return signal, score


def aggregate(results: list[CycleResult]) -> list[CycleResult]:
    """
    Compute and write consensus into each CycleResult in-place.
    Returns the same list for chaining convenience.
    """
    for result in results:
        signal, score = compute_consensus(result)
        result.consensus_signal = signal
        result.consensus_score  = score
        log.debug(
            "%s consensus: %s (score=%+.4f)  TV=%s  YF=%s",
            result.ticker,
            signal,
            score,
            result.tradingview.signal if result.tradingview else "N/A",
            result.yfinance.signal    if result.yfinance    else "N/A",
        )
    return results
