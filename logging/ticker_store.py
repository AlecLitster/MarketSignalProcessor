"""
logging/ticker_store.py
-----------------------
Per-ticker JSON history store.

One JSON file per ticker at logs/tickers/{TICKER}.json.
Each file is a list of CycleResult.as_dict() entries, ordered
oldest → newest, capped at MAX_TICKER_HISTORY_CYCLES entries.

This file is:
  - Read by core/swing.py for swing detection baseline
  - Read by ai/claude.py for historical context
  - Written by this module after every cycle
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from config.settings import (
    LOG_TICKER_DIR,
    MAX_TICKER_HISTORY_CYCLES,
    LOG_TICKER_JSON_ENABLED,
)
from core.models import CycleResult

log = logging.getLogger(__name__)


def _ticker_path(ticker: str) -> str:
    return os.path.join(LOG_TICKER_DIR, f"{ticker}.json")


def load_history(ticker: str) -> list[dict]:
    """
    Load the full history list for a ticker.
    Returns [] if no history exists or the file is corrupt.
    """
    path = _ticker_path(ticker)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        log.warning("Ticker store %s has unexpected format — resetting.", path)
        return []
    except (json.JSONDecodeError, IOError) as exc:
        log.error("Failed to load ticker history %s: %s", path, exc)
        return []


def save_result(result: CycleResult) -> None:
    """Append a CycleResult to the ticker's history file."""
    if not LOG_TICKER_JSON_ENABLED:
        return

    os.makedirs(LOG_TICKER_DIR, exist_ok=True)
    history = load_history(result.ticker)
    history.append(result.as_dict())

    # Trim to cap
    if len(history) > MAX_TICKER_HISTORY_CYCLES:
        history = history[-MAX_TICKER_HISTORY_CYCLES:]

    path = _ticker_path(result.ticker)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except IOError as exc:
        log.error("Failed to save ticker history %s: %s", path, exc)


def load_history_map(tickers: list[str]) -> dict[str, list[dict]]:
    """Load history for all tickers. Returns {ticker: [history entries]}."""
    return {ticker: load_history(ticker) for ticker in tickers}


def save_all(results: list[CycleResult]) -> None:
    """Save all cycle results to their respective ticker stores."""
    for result in results:
        save_result(result)
