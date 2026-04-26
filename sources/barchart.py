"""
sources/barchart.py
-------------------
BarChart signal source adapter.

Data acquisition strategy (tried in order):
  1. BarChart's internal JSON API  (/proxies/core-api/v1/quotes/get)
     — most reliable; requires a live session cookie (XSRF-TOKEN).
  2. Embedded JSON in the opinion page HTML (__NEXT_DATA__ / script tags).
  3. HTML table parsing fallback.

A single requests.Session is shared across all tickers so the XSRF cookie
is established once and reused. The session is refreshed automatically when
the API returns a 401/403.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config.settings import (
    BARCHART_BASE_URL,
    BARCHART_OPINION_PATH,
    BARCHART_OPINION_WEIGHTS,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    TRENDSPOTTER_STRENGTH_SCORE,
    BC_RETRY_ATTEMPTS,
    BC_RETRY_DELAY_SEC,
)
from config.indicators_barchart import (
    OPINION,
    MOVING_AVERAGES,
    OSCILLATORS,
    TREND,
    PRICE_VOLUME,
    TRENDSPOTTER,
    get_score_fn,
)
from core.models import IndicatorValue, SourceSignal, TrendSpotterSignal
from sources.base import SignalSource, TrendSpotterSource

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Referer":         "https://www.barchart.com",
}

# Fields requested from BarChart's internal API
_API_FIELDS = ",".join([
    "opinion_short", "opinion_medium", "opinion_long", "opinion_overall",
    "signal_strength", "signal_direction",
    "trendspotter", "trendspotter_strength", "trendspotter_change",
    "trendspotter_date", "days_in_signal",
    "ma20", "ma50", "ma100", "ma200",
    "ema20", "ema50", "ema100", "ema200",
    "rsi14", "stochasticK", "stochasticD", "williamsPercentR",
    "cci", "momentum", "macd", "macdSignal", "macdHistogram",
    "adx", "adxPlusDI", "adxMinusDI",
    "lastPrice", "open", "high", "low", "volume", "avgVolume",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "percentChange",
])

# Normalise any camelCase API keys → bc_field names used in the indicator registry
_API_KEY_MAP = {
    "signalStrength":       "signal_strength",
    "signalDirection":      "signal_direction",
    "trendSpotter":         "trendspotter",
    "trendspotterStrength": "trendspotter_strength",
    "trendSpotterStrength": "trendspotter_strength",
    "trendspotterChange":   "trendspotter_change",
    "trendSpotterChange":   "trendspotter_change",
    "trendspotterDate":     "trendspotter_date",
    "trendSpotterDate":     "trendspotter_date",
    "daysInSignal":         "days_in_signal",
}


class BarChartSource(SignalSource, TrendSpotterSource):

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._session_initialised = False

    @property
    def name(self) -> str:
        return "barchart"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, exchange: str) -> Optional[SourceSignal]:
        """Fetch BarChart Opinion and indicators → SourceSignal."""
        data = self._get_opinion_data(ticker)
        if data is None:
            return None
        return self._build_source_signal(ticker, data)

    def fetch_trendspotter(self, ticker: str) -> Optional[TrendSpotterSignal]:
        """Fetch BarChart TrendSpotter signal (reuses cached opinion data)."""
        data = self._get_opinion_data(ticker)
        if data is None:
            return None
        return self._build_trendspotter_signal(ticker, data)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> None:
        """Hit the BarChart homepage once to acquire the XSRF-TOKEN cookie."""
        if self._session_initialised:
            return
        try:
            self._session.get(BARCHART_BASE_URL, timeout=15)
            time.sleep(1)  # let BarChart's bot-detection settle before API calls
            self._session_initialised = True
            log.debug("BC: session established (XSRF=%s…)",
                      self._session.cookies.get("XSRF-TOKEN", "")[:8])
        except Exception as exc:
            log.warning("BC: could not establish session: %s", exc)

    def _reset_session(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._session_initialised = False
        self._ensure_session()

    # ------------------------------------------------------------------
    # Data acquisition (API → HTML fallback)
    # ------------------------------------------------------------------

    def _get_opinion_data(self, ticker: str) -> Optional[dict]:
        """
        Fetch opinion data for one ticker. Tries in order:
          1. BarChart internal JSON API (most reliable)
          2. Embedded JSON in the opinion page HTML
          3. HTML table parsing
        """
        self._ensure_session()

        for attempt in range(1, BC_RETRY_ATTEMPTS + 1):
            # -- Strategy 1: internal API --
            data = self._fetch_via_api(ticker)
            if data:
                return data

            # -- Strategy 2 & 3: page scrape --
            data = self._scrape_opinion_page(ticker)
            if data:
                return data

            log.warning("BC: no parseable data for %s on attempt %d", ticker, attempt)
            if attempt < BC_RETRY_ATTEMPTS:
                time.sleep(BC_RETRY_DELAY_SEC)

        log.error("BC: all attempts failed for %s", ticker)
        return None

    def _fetch_via_api(self, ticker: str) -> Optional[dict]:
        """
        Call BarChart's internal quote API.
        Requires a valid XSRF-TOKEN cookie from the homepage visit.
        """
        xsrf = self._session.cookies.get("XSRF-TOKEN", "")
        url  = (
            f"{BARCHART_BASE_URL}/proxies/core-api/v1/quotes/get"
            f"?symbols={ticker}&fields={_API_FIELDS}&raw=1"
        )
        headers = {
            "Accept":       "application/json",
            "X-XSRF-TOKEN": xsrf,
            "Referer":      f"{BARCHART_BASE_URL}/stocks/quotes/{ticker}/opinion",
        }
        try:
            resp = self._session.get(url, headers=headers, timeout=15)

            if resp.status_code in (401, 403):
                log.debug("BC API auth failed for %s — resetting session", ticker)
                self._reset_session()
                return None

            if not resp.ok:
                log.debug("BC API %s status=%d", ticker, resp.status_code)
                return None

            body = resp.json()
            rows = body.get("data", [])
            if not rows:
                return None

            row = rows[0]
            # API may nest raw values under a "raw" key
            raw_data = row.get("raw") if isinstance(row.get("raw"), dict) else row
            return self._normalise_api_row(raw_data)

        except Exception as exc:
            log.debug("BC API exception for %s: %s", ticker, exc)
            return None

    def _normalise_api_row(self, row: dict) -> dict:
        """Remap any camelCase API keys to the bc_field names the registry expects."""
        result = dict(row)
        for api_key, bc_field in _API_KEY_MAP.items():
            if api_key in row and bc_field not in result:
                result[bc_field] = row[api_key]
        return result

    def _scrape_opinion_page(self, ticker: str) -> Optional[dict]:
        """Fetch the HTML opinion page and extract data via JSON or table parsing."""
        url = BARCHART_BASE_URL + BARCHART_OPINION_PATH.format(symbol=ticker)
        try:
            resp = self._session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning("BC page fetch %s: %s", ticker, exc)
            return None

        data = self._extract_json_from_page(resp.text, ticker)
        if not data:
            data = self._extract_html_data(resp.text, ticker)
        return data

    def _extract_json_from_page(self, html: str, ticker: str) -> Optional[dict]:
        """Try several embedded-JSON patterns in the page source."""
        soup = BeautifulSoup(html, "lxml")

        # Next.js / React SSR: data embedded in <script id="__NEXT_DATA__">
        next_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_tag and next_tag.string:
            try:
                raw = json.loads(next_tag.string)
                data = self._normalise_next_data(raw)
                if data:
                    return data
            except json.JSONDecodeError:
                pass

        # Legacy patterns: window.__PRELOADED_STATE__ or window.pageData
        patterns = [
            r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\})\s*;',
            r'window\.pageData\s*=\s*(\{.+?\})\s*;',
            r'var\s+pageData\s*=\s*(\{.+?\})\s*;',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    raw = json.loads(match.group(1))
                    data = self._normalise_json_blob(raw)
                    if data:
                        return data
                except json.JSONDecodeError:
                    continue

        return None

    def _normalise_next_data(self, blob: dict) -> Optional[dict]:
        """Navigate Next.js __NEXT_DATA__ structure to find opinion fields."""
        # Walk common paths: props → pageProps → ... → quote / technicals
        def _dig(d: dict, *keys):
            for k in keys:
                if not isinstance(d, dict):
                    return None
                d = d.get(k, {})
            return d if isinstance(d, dict) else None

        candidates = [
            _dig(blob, "props", "pageProps", "quote"),
            _dig(blob, "props", "pageProps", "technicals"),
            _dig(blob, "props", "pageProps", "pageData"),
            _dig(blob, "props", "initialState", "quote"),
        ]
        for candidate in candidates:
            if candidate:
                data = self._normalise_json_blob(candidate)
                if data:
                    return data
        return None

    def _normalise_json_blob(self, blob: dict) -> Optional[dict]:
        """Flatten a raw JSON blob into canonical bc_field → value mapping."""
        result = {}

        opinion = (
            blob.get("opinion")
            or blob.get("technicalSummary")
            or blob.get("technical", {}).get("opinion")
            or {}
        )

        field_map = {
            "shortTermSignal":      "opinion_short",
            "mediumTermSignal":     "opinion_medium",
            "longTermSignal":       "opinion_long",
            "overallSignal":        "opinion_overall",
            "signalStrength":       "signal_strength",
            "signalDirection":      "signal_direction",
            "trendSpotter":         "trendspotter",
            "trendSpotterStrength": "trendspotter_strength",
            "trendSpotterChange":   "trendspotter_change",
        }
        for json_key, bc_field in field_map.items():
            val = opinion.get(json_key)
            if val is not None:
                result[bc_field] = val

        # Also accept flat keys that already match bc_field names
        flat_keys = [
            "opinion_short", "opinion_medium", "opinion_long", "opinion_overall",
            "signal_strength", "signal_direction", "trendspotter",
            "trendspotter_strength", "trendspotter_change", "trendspotter_date",
            "days_in_signal",
            "ma20", "ma50", "ma100", "ma200", "ema20", "ema50", "ema100", "ema200",
            "rsi14", "stochasticK", "stochasticD", "williamsPercentR", "cci",
            "momentum", "macd", "macdSignal", "macdHistogram",
            "adx", "adxPlusDI", "adxMinusDI",
            "lastPrice", "open", "high", "low", "volume", "avgVolume",
            "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "percentChange",
        ]
        for key in flat_keys:
            if key not in result and key in blob:
                result[key] = blob[key]

        quote = blob.get("quote") or blob.get("price") or {}
        price_map = {
            "lastPrice": "lastPrice", "close": "lastPrice",
            "open": "open", "high": "high", "low": "low",
            "volume": "volume", "avgVolume": "avgVolume",
            "fiftyTwoWeekHigh": "fiftyTwoWeekHigh",
            "fiftyTwoWeekLow":  "fiftyTwoWeekLow",
            "percentChange":    "percentChange",
        }
        for json_key, bc_field in price_map.items():
            val = quote.get(json_key)
            if val is not None and bc_field not in result:
                result[bc_field] = val

        return result if result else None

    def _extract_html_data(self, html: str, ticker: str) -> Optional[dict]:
        """Last-resort: parse opinion values from rendered HTML tables."""
        try:
            soup   = BeautifulSoup(html, "lxml")
            result = {}

            opinion_map = {
                "Short-Term":  "opinion_short",
                "Medium-Term": "opinion_medium",
                "Long-Term":   "opinion_long",
                "Overall":     "opinion_overall",
            }
            for row in soup.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if label in opinion_map:
                        result[opinion_map[label]] = value

            ts_section = (
                soup.find("div", {"data-ng-controller": "TrendSpotterController"})
                or soup.find(class_=re.compile(r"trendspotter", re.I))
            )
            if ts_section:
                ts_text = ts_section.get_text(separator=" ", strip=True)
                for keyword in ("Buy", "Sell", "Hold"):
                    if keyword in ts_text:
                        result["trendspotter"] = keyword
                        break

            price_tag = soup.find(class_=re.compile(r"last-price|lastPrice|quote-price", re.I))
            if price_tag:
                price_str = re.sub(r"[^\d.]", "", price_tag.get_text())
                try:
                    result["lastPrice"] = float(price_str)
                except ValueError:
                    pass

            return result if result else None

        except Exception as exc:
            log.warning("BC HTML parse failed for %s: %s", ticker, exc)
            return None

    # ------------------------------------------------------------------
    # Signal construction
    # ------------------------------------------------------------------

    def _build_source_signal(self, ticker: str, data: dict) -> Optional[SourceSignal]:
        """Build SourceSignal from scraped data dict."""
        price = self._safe_float(data.get("lastPrice"))

        # Process all indicator categories
        indicators = {
            "opinion":         self._process_category(OPINION,         data, price),
            "moving_averages": self._process_category(MOVING_AVERAGES, data, price),
            "oscillators":     self._process_category(OSCILLATORS,     data, price),
            "trend":           self._process_category(TREND,           data, price),
            "price_volume":    self._process_category(PRICE_VOLUME,    data, price),
        }

        # Compute timeframe signals and weighted score from opinion fields
        score, timeframe_signals = self._compute_score(data)
        signal = self._score_to_signal(score)

        # Count buy/sell/neutral from all scored indicators
        buy_count = sell_count = neutral_count = 0
        for ivs in indicators.values():
            for iv in ivs:
                if iv.signal in ("BUY",):
                    buy_count += 1
                elif iv.signal == "SELL":
                    sell_count += 1
                elif iv.signal in ("NEUTRAL", "OVERBOUGHT", "OVERSOLD", "WEAK_TREND"):
                    neutral_count += 1

        return SourceSignal(
            source            = self.name,
            ticker            = ticker,
            timestamp         = datetime.now(),
            signal            = signal,
            score             = round(score, 4),
            price             = price,
            timeframe_signals = timeframe_signals,
            indicators        = indicators,
            buy_count         = buy_count,
            sell_count        = sell_count,
            neutral_count     = neutral_count,
            raw               = data,
        )

    def _compute_score(self, data: dict) -> tuple[float, dict]:
        """Compute weighted score from BarChart opinion timeframe fields."""
        opinion_field_map = {
            "long":   "opinion_long",
            "medium": "opinion_medium",
            "short":  "opinion_short",
        }
        score_map = {
            "strong buy":  1.0,
            "buy":         0.5,
            "hold":        0.0,
            "sell":       -0.5,
            "strong sell": -1.0,
        }
        weighted_score    = 0.0
        timeframe_signals = {}
        total_weight      = 0.0

        for tf, field in opinion_field_map.items():
            weight  = BARCHART_OPINION_WEIGHTS.get(tf, 0.0)
            raw_val = data.get(field)
            if raw_val is None:
                timeframe_signals[tf] = "N/A"
                continue
            normalised = str(raw_val).lower().strip()
            score      = score_map.get(normalised, 0.0)
            weighted_score    += score * weight
            total_weight      += weight
            timeframe_signals[tf] = str(raw_val).title()

        # Normalise if not all timeframes were present
        if 0 < total_weight < 1.0:
            weighted_score /= total_weight

        return weighted_score, timeframe_signals

    def _score_to_signal(self, score: float) -> str:
        if score >= BUY_THRESHOLD:
            return "BUY"
        if score <= SELL_THRESHOLD:
            return "SELL"
        return "HOLD"

    def _build_trendspotter_signal(
        self,
        ticker: str,
        data: dict,
    ) -> Optional[TrendSpotterSignal]:
        """Build TrendSpotterSignal from scraped data dict."""
        raw_signal   = data.get("trendspotter")
        raw_strength = data.get("trendspotter_strength")
        raw_change   = data.get("trendspotter_change")
        raw_date     = data.get("trendspotter_date")
        raw_days     = data.get("days_in_signal")

        if raw_signal is None:
            log.debug("BC: no TrendSpotter signal found for %s", ticker)
            return None

        signal_str   = str(raw_signal).strip().title()
        signal       = {"Buy": "BUY", "Sell": "SELL", "Hold": "HOLD"}.get(signal_str, "HOLD")
        strength_str = str(raw_strength).upper().strip() if raw_strength else "N/A"
        change_str   = str(raw_change).upper().strip()   if raw_change   else "N/A"

        # Score = direction × strength magnitude
        base_magnitude  = TRENDSPOTTER_STRENGTH_SCORE.get(strength_str, 0.5)
        score           = base_magnitude if signal == "BUY" else (-base_magnitude if signal == "SELL" else 0.0)

        days = None
        if raw_days is not None:
            try:
                days = int(raw_days)
            except (TypeError, ValueError):
                pass

        return TrendSpotterSignal(
            ticker         = ticker,
            timestamp      = datetime.now(),
            signal         = signal,
            score          = round(score, 4),
            strength       = strength_str,
            change         = change_str,
            signal_date    = str(raw_date) if raw_date else None,
            days_in_signal = days,
            raw            = data,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _process_category(
        self,
        registry: list[dict],
        data: dict,
        price: Optional[float],
    ) -> list[IndicatorValue]:
        """Process one indicator category through the scoring registry."""
        results = []
        # Inject price so ma_vs_price can compare
        data_with_price = {**data, "close": price} if price else data

        for entry in registry:
            bc_field = entry["bc_field"]
            raw_val  = data.get(bc_field)
            score_fn = get_score_fn(entry["score_fn"])
            fval     = self._safe_float(raw_val)
            signal   = score_fn(fval, data_with_price, entry["params"])

            results.append(IndicatorValue(
                key    = entry["key"],
                value  = fval,
                signal = signal,
            ))
        return results

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return round(float(str(value).replace(",", "").replace("%", "")), 6)
        except (TypeError, ValueError):
            return None
