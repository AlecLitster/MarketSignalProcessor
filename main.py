"""
main.py
-------
MarketSignalProcessor orchestrator.

Per-cycle pipeline for each ticker:
  1. Load per-ticker history from JSON store
  2. Fetch signals from all enabled sources (TradingView, YFinance)
  3. Compute weighted consensus
  4. Detect swing events vs. rolling history baseline
  5. Generate Claude AI synopsis (only for non-HOLD signals or detected swings)
  6. Persist to JSON store + CSV
  7. Push signal_summary rows to the live dashboard

Run:
  python main.py

Set TRADING_ENABLED=true in .env only when the Schwab broker is fully
implemented and tested — it defaults to false as a safety gate.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from config.settings import (
    TICKERS,
    POLLING_INTERVAL_SECONDS,
    TRADINGVIEW_ENABLED,
    YFINANCE_ENABLED,
    CLAUDE_AI_SYNOPSIS_ENABLED,
    AI_HISTORY_CYCLES,
    TRADING_ENABLED,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    TV_TICKER_DELAY_SEC,
    TV_STARTUP_DELAY_SEC,
)
from core.models import CycleResult
from core.aggregator import aggregate
from core.swing import detect_swings
from stores.ticker_store import load_history_map, save_all
from stores.csv_log import write as write_csv
from stores.ai_prompt_log import write as write_ai_prompt
import dashboard.server as dashboard

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Source initialisation (lazy — imported only when enabled)
# ---------------------------------------------------------------------------

_tv_source  = None
_yf_source  = None
_ai         = None

if TRADINGVIEW_ENABLED:
    from sources.tradingview import TradingViewSource
    _tv_source = TradingViewSource()

if YFINANCE_ENABLED:
    from sources.yfinance_source import YFinanceSource
    _yf_source = YFinanceSource()

if CLAUDE_AI_SYNOPSIS_ENABLED:
    from ai.claude import ClaudeInterpreter
    _ai = ClaudeInterpreter()


# ---------------------------------------------------------------------------
# Single-ticker fetch
# ---------------------------------------------------------------------------

def _fetch_one(ticker: dict) -> CycleResult:
    symbol   = ticker["symbol"]
    exchange = ticker["exchange"]
    result   = CycleResult(ticker=symbol, timestamp=datetime.now())

    if _tv_source:
        result.tradingview = _tv_source.fetch(symbol, exchange)

    if _yf_source:
        result.yfinance = _yf_source.fetch(symbol, exchange)

    return result


def _maybe_add_ai(result: CycleResult, history: list[dict]) -> None:
    if _ai is None:
        return
    # Skip AI for confident HOLDs with no swing — saves tokens
    if result.consensus_signal == "HOLD" and not result.has_swing:
        return
    result.ai = _ai.interpret(result, history)


# ---------------------------------------------------------------------------
# Full polling cycle
# ---------------------------------------------------------------------------

def run_cycle() -> None:
    log.info("━━━ Cycle start (%d tickers) ━━━", len(TICKERS))
    symbols     = [t["symbol"] for t in TICKERS]
    history_map = load_history_map(symbols)

    results: list[CycleResult] = []
    for i, ticker in enumerate(TICKERS):
        results.append(_fetch_one(ticker))
        if TRADINGVIEW_ENABLED and i < len(TICKERS) - 1:
            time.sleep(TV_TICKER_DELAY_SEC)
    aggregate(results)
    detect_swings(results, history_map)

    for result in results:
        history = history_map.get(result.ticker, [])
        _maybe_add_ai(result, history[-AI_HISTORY_CYCLES:])

        log.info(
            "%-8s  %s  score=%+.4f  TV=%-5s  YF=%-5s  AI=%-5s  swing=%s",
            result.ticker,
            result.consensus_signal,
            result.consensus_score,
            getattr(result.tradingview, "signal", "N/A"),
            getattr(result.yfinance,    "signal", "N/A"),
            getattr(result.ai,           "signal", "—"),
            result.swing_event.label if result.swing_event else "—",
        )

    save_all(results)
    write_csv(results)
    write_ai_prompt(results)
    dashboard.update([r.signal_summary for r in results])
    log.info("━━━ Cycle done ━━━")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if TRADING_ENABLED:
        log.warning("⚠  TRADING IS ENABLED — live orders can be placed.")
    else:
        log.info("Trading disabled (read-only mode).")

    dashboard.start(host=DASHBOARD_HOST, port=DASHBOARD_PORT)

    if TRADINGVIEW_ENABLED and TV_STARTUP_DELAY_SEC > 0:
        log.info("Waiting %ds for TradingView rate-limit to clear before first cycle …", int(TV_STARTUP_DELAY_SEC))
        time.sleep(TV_STARTUP_DELAY_SEC)

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log.info("Shutting down.")
            break
        except Exception as exc:
            log.error("Cycle failed: %s", exc, exc_info=True)

        log.info("Sleeping %ds until next cycle.", POLLING_INTERVAL_SECONDS)
        try:
            time.sleep(POLLING_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            log.info("Shutting down.")
            break


if __name__ == "__main__":
    main()
