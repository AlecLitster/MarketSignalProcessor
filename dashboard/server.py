"""
dashboard/server.py
-------------------
Live dashboard HTTP server (Flask).

Serves the static dashboard and three JSON API endpoints:
  GET /              → index.html
  GET /api/signals   → latest signal_summary for every ticker
  GET /api/history/<ticker> → full per-ticker JSON history
  GET /api/status    → service metadata

Call update() from the main polling loop to push fresh data.
Call start() once at startup to launch Flask in a daemon thread.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from flask import Flask, jsonify, send_from_directory

from config.settings import DASHBOARD_HOST, DASHBOARD_PORT, LOG_TICKER_DIR, TICKERS

log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["JSON_SORT_KEYS"] = False

_latest_signals: list[dict] = []
_lock = threading.Lock()
_start_time: str = ""


# ---------------------------------------------------------------------------
# Called by main.py
# ---------------------------------------------------------------------------

def update(signal_summaries: list[dict]) -> None:
    """Push latest cycle data. Thread-safe."""
    with _lock:
        _latest_signals.clear()
        _latest_signals.extend(signal_summaries)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/signals")
def get_signals():
    with _lock:
        data = list(_latest_signals)
    return jsonify(data)


@app.route("/api/history/<ticker>")
def get_history(ticker: str):
    path = os.path.join(LOG_TICKER_DIR, f"{ticker.upper()}.json")
    if not os.path.exists(path):
        return jsonify([])
    try:
        with open(path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as exc:
        log.warning("Could not read history for %s: %s", ticker, exc)
        return jsonify([])


@app.route("/api/status")
def get_status():
    symbols = [t["symbol"] if isinstance(t, dict) else t for t in TICKERS]
    with _lock:
        signal_count = len(_latest_signals)
    return jsonify({
        "status":       "running",
        "start_time":   _start_time,
        "ticker_count": len(symbols),
        "signal_count": signal_count,
        "tickers":      symbols,
    })


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _load_last_signals() -> None:
    """Pre-populate _latest_signals from the most recent entry in each ticker's JSON store."""
    symbols = [t["symbol"] if isinstance(t, dict) else t for t in TICKERS]
    summaries = []
    for symbol in symbols:
        path = os.path.join(LOG_TICKER_DIR, f"{symbol}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
            if not history:
                continue
            last = history[-1]
            tv   = last.get("tradingview") or {}
            yf   = last.get("yfinance")    or {}
            ai   = last.get("ai")           or {}
            sw   = last.get("swing_event")  or {}
            price = (tv.get("price") if tv.get("price") is not None
                     else yf.get("price"))
            summaries.append({
                "ticker":           symbol,
                "price":            price,
                "tv_signal":        tv.get("signal", "N/A"),
                "tv_score":         tv.get("score"),
                "yf_signal":        yf.get("signal", "N/A"),
                "yf_score":         yf.get("score"),
                "ai_signal":        ai.get("signal",   "N/A"),
                "ai_confidence":    ai.get("confidence", "N/A"),
                "ai_price_target":  ai.get("price_target"),
                "ai_target_date":   ai.get("target_date"),
                "consensus_signal": last.get("consensus_signal", "N/A"),
                "consensus_score":  last.get("consensus_score",  0.0),
                "swing_label":      sw.get("label"),
                "timestamp":        last.get("timestamp", ""),
            })
        except Exception as exc:
            log.debug("Could not pre-load history for %s: %s", symbol, exc)

    if summaries:
        with _lock:
            _latest_signals.clear()
            _latest_signals.extend(summaries)
        log.info("Dashboard pre-loaded last known signals for %d ticker(s)", len(summaries))


def start(host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT) -> threading.Thread:
    """Launch Flask in a background daemon thread."""
    global _start_time
    from datetime import datetime
    _start_time = datetime.now().isoformat(timespec="seconds")

    _load_last_signals()

    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
        name="dashboard",
    )
    t.start()
    log.info("Dashboard → http://%s:%d", host, port)
    return t
