"""
sources/barchart.py
-------------------
BarChart signal source adapter — web scraping implementation.

Scrapes the BarChart opinion page for:
  - BC Opinion Signal (Signal #2)        → SourceSignal
  - BarChart TrendSpotter (Signal #3)    → TrendSpotterSignal

When BARCHART_ACCESS_MODE = "api", swap _scrape_opinion() and
_scrape_trendspotter() for API equivalents. The public fetch() and
fetch_trendspotter() interfaces stay identical — no other file changes.

Note on scraping:
  BarChart's opinion page is JavaScript-rendered. We request the page
  with a browser-like User-Agent and parse the embedded JSON data
  that BarChart injects into the page as a <script> tag. This is more
  reliable than parsing rendered HTML but may break if BarChart changes
  their page structure. If scraping fails, the adapter returns None
  gracefully and logs a warning.
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


class BarChartSource(SignalSource, TrendSpotterSource):

    @property
    def name(self) -> str:
        return "barchart"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, exchange: str) -> Optional[SourceSignal]:
        """Fetch BarChart Opinion and indicators → SourceSignal."""
        data = self._scrape_opinion(ticker)
        if data is None:
            return None
        return self._build_source_signal(ticker, data)

    def fetch_trendspotter(self, ticker: str) -> Optional[TrendSpotterSignal]:
        """Fetch BarChart TrendSpotter signal."""
        data = self._scrape_opinion(ticker)
        if data is None:
            return None
        return self._build_trendspotter_signal(ticker, data)

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def _scrape_opinion(self, ticker: str) -> Optional[dict]:
        """
        Scrape the BarChart opinion page and extract embedded JSON data.
        Returns a flat dict of field_name → value, or None on failure.
        """
        url = BARCHART_BASE_URL + BARCHART_OPINION_PATH.format(symbol=ticker)

        for attempt in range(1, BC_RETRY_ATTEMPTS + 1):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=20)
                resp.raise_for_status()
                data = self._parse_opinion_page(resp.text, ticker)
                if data:
                    return data
                log.warning("BC: no parseable data for %s on attempt %d", ticker, attempt)
            except requests.RequestException as exc:
                log.warning(
                    "BC scrape %s attempt %d/%d: %s",
                    ticker, attempt, BC_RETRY_ATTEMPTS, exc,
                )
            if attempt < BC_RETRY_ATTEMPTS:
                time.sleep(BC_RETRY_DELAY_SEC)

        log.error("BC: all scrape attempts failed for %s", ticker)
        return None

    def _parse_opinion_page(self, html: str, ticker: str) -> Optional[dict]:
        """
        Extract opinion data from BarChart page HTML.

        BarChart embeds data in multiple places:
          1. A JSON blob in a <script> tag with window.bcApp or similar
          2. Structured HTML tables in the opinion section

        We try JSON extraction first (more reliable), fall back to HTML parsing.
        """
        data = self._extract_json_data(html, ticker)
        if not data:
            data = self._extract_html_data(html, ticker)
        return data

    def _extract_json_data(self, html: str, ticker: str) -> Optional[dict]:
        """Try to find and parse embedded JSON data blobs."""
        patterns = [
            r'window\.__PRELOADED_STATE__\s*=\s*({.+?});\s*</script>',
            r'"technicalSummary"\s*:\s*({[^}]+})',
            r'"opinion"\s*:\s*({[^}]+})',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    raw = json.loads(match.group(1))
                    extracted = self._normalise_json_blob(raw)
                    if extracted:
                        return extracted
                except (json.JSONDecodeError, KeyError):
                    continue
        return None

    def _normalise_json_blob(self, blob: dict) -> Optional[dict]:
        """
        Flatten a raw JSON blob into canonical bc_field → value mapping.
        Handles nested structures from different BarChart JSON layouts.
        """
        result = {}

        # Try common paths for opinion data
        opinion = (
            blob.get("opinion")
            or blob.get("technicalSummary")
            or blob.get("technical", {}).get("opinion")
            or {}
        )

        field_map = {
            "strongBuy":     "opinion_short",
            "shortTermSignal": "opinion_short",
            "mediumTermSignal": "opinion_medium",
            "longTermSignal":  "opinion_long",
            "overallSignal":   "opinion_overall",
            "signalStrength":  "signal_strength",
            "signalDirection": "signal_direction",
            "trendSpotter":    "trendspotter",
            "trendSpotterStrength": "trendspotter_strength",
            "trendSpotterChange":   "trendspotter_change",
        }

        for json_key, bc_field in field_map.items():
            val = opinion.get(json_key)
            if val is not None:
                result[bc_field] = val

        # Price data
        quote = blob.get("quote") or blob.get("price") or {}
        price_map = {
            "lastPrice": "lastPrice",
            "close":     "lastPrice",
            "open":      "open",
            "high":      "high",
            "low":       "low",
            "volume":    "volume",
            "avgVolume": "avgVolume",
            "fiftyTwoWeekHigh": "fiftyTwoWeekHigh",
            "fiftyTwoWeekLow":  "fiftyTwoWeekLow",
            "percentChange":    "percentChange",
        }
        for json_key, bc_field in price_map.items():
            val = quote.get(json_key)
            if val is not None:
                result[bc_field] = val

        return result if result else None

    def _extract_html_data(self, html: str, ticker: str) -> Optional[dict]:
        """
        Fallback: parse structured HTML tables from the opinion page.
        Less reliable than JSON extraction but works when JSON is absent.
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            result = {}

            # Opinion signal rows — look for the opinion summary section
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

            # TrendSpotter — typically in a dedicated section
            ts_section = soup.find("div", {"data-ng-controller": "TrendSpotterController"}) \
                      or soup.find(class_=re.compile(r"trendspotter", re.I))
            if ts_section:
                ts_text = ts_section.get_text(separator=" ", strip=True)
                for keyword in ["Buy", "Sell", "Hold"]:
                    if keyword in ts_text:
                        result["trendspotter"] = keyword
                        break

            # Last price — look for common price display patterns
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
