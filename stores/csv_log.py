"""
stores/csv_log.py
-----------------
Machine-readable aggregate CSV log.

One row per ticker per cycle. Flat, wide format — suitable for
pandas, Excel, or downstream ML pipelines.

Columns:
  timestamp, ticker, price,
  tv_signal, tv_score, tv_buy, tv_sell, tv_neutral,
  bc_signal, bc_score, bc_buy, bc_sell, bc_neutral,
  ts_signal, ts_strength, ts_score, ts_days,
  ai_signal, ai_confidence, ai_price_target,
  ai_price_target_low, ai_price_target_high,
  ai_target_date, ai_target_date_range,
  consensus_signal, consensus_score,
  swing_label, swing_delta

Rotated at LOG_CSV_MAX_BYTES with LOG_BACKUP_COUNT compressed backups.
"""

from __future__ import annotations

import csv
import gzip
import logging
import os
import shutil

from config.settings import (
    LOG_CSV_FILE,
    LOG_CSV_MAX_BYTES,
    LOG_BACKUP_COUNT,
    LOG_CSV_ENABLED,
)
from core.models import CycleResult

log = logging.getLogger(__name__)

_COLUMNS = [
    "timestamp", "ticker", "price",
    "tv_signal", "tv_score", "tv_buy", "tv_sell", "tv_neutral",
    "bc_signal", "bc_score", "bc_buy", "bc_sell", "bc_neutral",
    "ts_signal", "ts_strength", "ts_score", "ts_days",
    "ai_signal", "ai_confidence", "ai_price_target",
    "ai_price_target_low", "ai_price_target_high",
    "ai_target_date", "ai_target_date_range",
    "consensus_signal", "consensus_score",
    "swing_label", "swing_delta",
]


def _rotate(path: str) -> None:
    """Rotate log file if it exceeds size cap."""
    if not os.path.exists(path) or os.path.getsize(path) < LOG_CSV_MAX_BYTES:
        return
    oldest = f"{path}.{LOG_BACKUP_COUNT}.gz"
    if os.path.exists(oldest):
        os.remove(oldest)
    for n in range(LOG_BACKUP_COUNT - 1, 0, -1):
        src = f"{path}.{n}.gz"
        dst = f"{path}.{n + 1}.gz"
        if os.path.exists(src):
            shutil.move(src, dst)
    with open(path, "rb") as f_in, gzip.open(f"{path}.1.gz", "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    open(path, "w").close()


def _ensure_header() -> None:
    """Write CSV header if the file is new or empty."""
    if not os.path.exists(LOG_CSV_FILE) or os.path.getsize(LOG_CSV_FILE) == 0:
        with open(LOG_CSV_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_COLUMNS)


def _result_to_row(result: CycleResult) -> dict:
    """Flatten a CycleResult into a CSV row dict."""
    tv = result.tradingview
    bc = result.barchart
    ts = result.trendspotter
    ai = result.ai
    sw = result.swing_event

    return {
        "timestamp":            result.timestamp.isoformat(),
        "ticker":               result.ticker,
        "price":                result.price,
        "tv_signal":            tv.signal        if tv else "",
        "tv_score":             tv.score         if tv else "",
        "tv_buy":               tv.buy_count      if tv else "",
        "tv_sell":              tv.sell_count     if tv else "",
        "tv_neutral":           tv.neutral_count  if tv else "",
        "bc_signal":            bc.signal        if bc else "",
        "bc_score":             bc.score         if bc else "",
        "bc_buy":               bc.buy_count      if bc else "",
        "bc_sell":              bc.sell_count     if bc else "",
        "bc_neutral":           bc.neutral_count  if bc else "",
        "ts_signal":            ts.signal        if ts else "",
        "ts_strength":          ts.strength      if ts else "",
        "ts_score":             ts.score         if ts else "",
        "ts_days":              ts.days_in_signal if ts else "",
        "ai_signal":            ai.signal               if ai else "",
        "ai_confidence":        ai.confidence           if ai else "",
        "ai_price_target":      ai.price_target         if ai else "",
        "ai_price_target_low":  ai.price_target_low     if ai else "",
        "ai_price_target_high": ai.price_target_high    if ai else "",
        "ai_target_date":       ai.target_date          if ai else "",
        "ai_target_date_range": ai.target_date_range    if ai else "",
        "consensus_signal":     result.consensus_signal,
        "consensus_score":      result.consensus_score,
        "swing_label":          sw.label       if sw else "",
        "swing_delta":          sw.score_delta if sw else "",
    }


def write(results: list[CycleResult]) -> None:
    """Append one row per result to the CSV log."""
    if not LOG_CSV_ENABLED:
        return

    os.makedirs(os.path.dirname(LOG_CSV_FILE), exist_ok=True)
    _rotate(LOG_CSV_FILE)
    _ensure_header()

    try:
        with open(LOG_CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            for result in results:
                writer.writerow(_result_to_row(result))
    except IOError as exc:
        log.error("CSV log write failed: %s", exc)
