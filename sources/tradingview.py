"""
sources/tradingview.py
----------------------
TradingView signal source adapter.

Fetches technical analysis for all configured timeframes using the
tradingview_ta library, then processes every indicator defined in
config/indicators_tradingview.py into a normalised SourceSignal.

All indicator keys are registry-driven — add new indicators to
config/indicators_tradingview.py, not here.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from tradingview_ta import TA_Handler, Interval

from config.settings import (
    TRADINGVIEW_SCREENER,
    TRADINGVIEW_TIMEFRAMES,
    TRADINGVIEW_TIMEFRAME_WEIGHTS,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    SIGNAL_SCORE_MAP,
    TV_RETRY_ATTEMPTS,
    TV_RETRY_DELAY_SEC,
    TV_CALL_DELAY_SEC,
)
from config.indicators_tradingview import (
    MOVING_AVERAGES,
    OSCILLATORS,
    TREND,
    VOLUME,
    PIVOT_TYPES,
    PIVOT_LEVELS,
    PIVOT_DISPLAY,
    SUMMARY_FIELDS,
    pivot_tv_key,
    get_score_fn,
)
from core.models import IndicatorValue, SourceSignal
from sources.base import SignalSource

log = logging.getLogger(__name__)


class TradingViewSource(SignalSource):

    @property
    def name(self) -> str:
        return "tradingview"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, exchange: str) -> Optional[SourceSignal]:
        """Fetch all timeframes and return a normalised SourceSignal."""
        timeframe_analyses = {}

        for label, interval in TRADINGVIEW_TIMEFRAMES.items():
            analysis = self._fetch_with_retry(ticker, exchange, interval, label)
            timeframe_analyses[label] = analysis
            if label != list(TRADINGVIEW_TIMEFRAMES.keys())[-1]:
                time.sleep(TV_CALL_DELAY_SEC)

        return self._build_signal(ticker, timeframe_analyses)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _fetch_with_retry(
        self,
        ticker: str,
        exchange: str,
        interval: Interval,
        label: str,
    ):
        """Fetch one timeframe with retry logic. Returns analysis or None."""
        for attempt in range(1, TV_RETRY_ATTEMPTS + 1):
            try:
                handler = TA_Handler(
                    symbol=ticker,
                    screener=TRADINGVIEW_SCREENER,
                    exchange=exchange,
                    interval=interval,
                )
                return handler.get_analysis()
            except Exception as exc:
                log.warning(
                    "TV fetch %s %s [%s] attempt %d/%d: %s",
                    ticker, label, interval, attempt, TV_RETRY_ATTEMPTS, exc,
                )
                if attempt < TV_RETRY_ATTEMPTS:
                    time.sleep(TV_RETRY_DELAY_SEC)

        log.error(
            "TV: all retries failed for %s %s — verify symbol and exchange are "
            "correct (screener=%s, exchange=%s)",
            ticker, label, TRADINGVIEW_SCREENER, exchange,
        )
        return None

    # ------------------------------------------------------------------
    # Signal construction
    # ------------------------------------------------------------------

    def _build_signal(
        self,
        ticker: str,
        timeframe_analyses: dict,
    ) -> Optional[SourceSignal]:
        """Build a SourceSignal from multi-timeframe analysis objects."""
        daily = timeframe_analyses.get("daily")
        if daily is None:
            log.error("TV: no daily analysis for %s — cannot build signal", ticker)
            return None

        weighted_score, timeframe_signals = self._compute_weighted_score(timeframe_analyses)
        signal = self._score_to_signal(weighted_score)

        raw_indicators = daily.indicators
        price          = raw_indicators.get("close")

        indicators = {
            "moving_averages": self._process_category(MOVING_AVERAGES, raw_indicators),
            "oscillators":     self._process_category(OSCILLATORS,     raw_indicators),
            "trend":           self._process_category(TREND,           raw_indicators),
            "volume":          self._process_category(VOLUME,          raw_indicators),
            "pivots":          self._process_pivots(raw_indicators),
        }

        summary      = daily.summary
        buy_count    = summary.get("BUY", 0)
        sell_count   = summary.get("SELL", 0)
        neutral_count= summary.get("NEUTRAL", 0)

        return SourceSignal(
            source            = self.name,
            ticker            = ticker,
            timestamp         = datetime.now(),
            signal            = signal,
            score             = round(weighted_score, 4),
            price             = price,
            timeframe_signals = timeframe_signals,
            indicators        = indicators,
            buy_count         = buy_count,
            sell_count        = sell_count,
            neutral_count     = neutral_count,
            raw               = {tf: (a.indicators if a else {}) for tf, a in timeframe_analyses.items()},
        )

    def _compute_weighted_score(self, timeframe_analyses: dict) -> tuple[float, dict]:
        """Compute weighted score across timeframes."""
        weighted_score    = 0.0
        timeframe_signals = {}

        for label, analysis in timeframe_analyses.items():
            weight = TRADINGVIEW_TIMEFRAME_WEIGHTS.get(label, 0.0)
            if analysis is None:
                timeframe_signals[label] = "N/A"
                continue
            rec   = analysis.summary.get("RECOMMENDATION", "NEUTRAL")
            score = SIGNAL_SCORE_MAP.get(rec.upper(), 0.0)
            weighted_score           += score * weight
            timeframe_signals[label]  = rec.replace("_", " ").title()

        return weighted_score, timeframe_signals

    def _score_to_signal(self, score: float) -> str:
        if score >= BUY_THRESHOLD:
            return "BUY"
        if score <= SELL_THRESHOLD:
            return "SELL"
        return "HOLD"

    # ------------------------------------------------------------------
    # Indicator processing
    # ------------------------------------------------------------------

    def _process_category(
        self,
        registry: list[dict],
        raw_indicators: dict,
    ) -> list[IndicatorValue]:
        """Process one category of indicators through the scoring registry."""
        results = []
        for entry in registry:
            tv_key   = entry["tv_key"]
            value    = raw_indicators.get(tv_key)
            score_fn = get_score_fn(entry["score_fn"])
            signal   = score_fn(value, raw_indicators, entry["params"])

            # Convert value to float if possible
            fval = None
            if value is not None:
                try:
                    fval = round(float(value), 6)
                except (TypeError, ValueError):
                    pass

            results.append(IndicatorValue(
                key    = entry["key"],
                value  = fval,
                signal = signal,
            ))
        return results

    def _process_pivots(self, raw_indicators: dict) -> list[IndicatorValue]:
        """Process all pivot point levels."""
        results = []
        for pivot_type in PIVOT_TYPES:
            for level in PIVOT_LEVELS:
                tv_key      = pivot_tv_key(pivot_type, level)
                display_lvl = PIVOT_DISPLAY.get(level, level)
                value       = raw_indicators.get(tv_key)
                fval        = None
                if value is not None:
                    try:
                        fval = round(float(value), 4)
                    except (TypeError, ValueError):
                        pass
                results.append(IndicatorValue(
                    key    = f"PIVOT_{pivot_type.upper()}_{display_lvl}",
                    value  = fval,
                    signal = "N/A",   # pivots are context only
                ))
        return results
