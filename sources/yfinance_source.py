"""
sources/yfinance_source.py
--------------------------
yfinance + pandas_ta signal source adapter.

Downloads daily OHLCV history with yfinance, computes a suite of pandas_ta
indicators, scores each indicator, and returns a normalised SourceSignal
compatible with the rest of the pipeline.

Indicator categories mirrored from TradingView for a consistent dashboard:
  moving_averages — SMA 20/50/200, EMA 9/21
  oscillators     — RSI 14, MACD 12/26/9, Stochastic 14/3/3
  trend           — ADX 14, Bollinger Bands 20/2
  volume          — OBV trend
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config.settings import (
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    YF_PERIOD,
    YF_INTERVAL,
    YF_MIN_PERIODS,
)
from config.indicators_yfinance import (
    INDICATORS,
    CATEGORIES,
    INDICATOR_WEIGHTS,
    col_sma, col_ema, col_rsi, col_macd, col_stoch, col_adx, col_bbands,
    score_price_vs_ma, score_rsi, score_macd, score_stoch,
    score_adx, score_bbands, score_obv, signal_to_score,
)
from core.models import IndicatorValue, SourceSignal
from sources.base import SignalSource

log = logging.getLogger(__name__)


class YFinanceSource(SignalSource):

    def __init__(self) -> None:
        self._df_cache: dict = {}

    @property
    def name(self) -> str:
        return "yfinance"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, exchange: str) -> Optional[SourceSignal]:
        """Download history, compute indicators, return SourceSignal."""
        try:
            import yfinance as yf
        except ImportError:
            log.error("yfinance not installed — run: pip install yfinance pandas_ta")
            return None

        try:
            import pandas_ta  # noqa: F401 — side-effect: adds .ta accessor to DataFrame
        except ImportError:
            log.error("pandas_ta not installed — run: pip install pandas_ta")
            return None

        df = self._download(yf, ticker)
        if df is None or len(df) < YF_MIN_PERIODS:
            log.warning("YF: insufficient data for %s (%d rows)", ticker, len(df) if df is not None else 0)
            self._df_cache.pop(ticker.upper(), None)
            return None

        df = self._apply_indicators(df)
        self._df_cache[ticker.upper()] = df
        return self._build_signal(ticker, df)

    # ------------------------------------------------------------------
    # Data download
    # ------------------------------------------------------------------

    def _download(self, yf, ticker: str):
        """Fetch OHLCV history. Returns DataFrame or None."""
        try:
            t   = yf.Ticker(ticker)
            df  = t.history(period=YF_PERIOD, interval=YF_INTERVAL, auto_adjust=True)
            if df is None or df.empty:
                log.warning("YF: empty history for %s", ticker)
                return None
            # Standardise column names to title-case
            df.columns = [c.title() for c in df.columns]
            # Ensure Close column exists
            if "Close" not in df.columns:
                log.warning("YF: no Close column for %s", ticker)
                return None
            return df
        except Exception as exc:
            log.error("YF: download failed for %s: %s", ticker, exc)
            return None

    # ------------------------------------------------------------------
    # Indicator computation
    # ------------------------------------------------------------------

    def _apply_indicators(self, df):
        """Append all pandas_ta indicator columns to df in-place."""
        try:
            df.ta.sma(length=20,  append=True)
            df.ta.sma(length=50,  append=True)
            df.ta.sma(length=200, append=True)
            df.ta.ema(length=9,   append=True)
            df.ta.ema(length=21,  append=True)
            df.ta.rsi(length=14,  append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.stoch(k=14, d=3, smooth_k=3, append=True)
            df.ta.adx(length=14,  append=True)
            df.ta.bbands(length=20, std=2.0, append=True)
            df.ta.obv(append=True)
            df.ta.supertrend(length=7, multiplier=3.0, append=True)
        except Exception as exc:
            log.warning("YF: indicator computation error: %s", exc)
        return df

    # ------------------------------------------------------------------
    # Signal construction
    # ------------------------------------------------------------------

    def _build_signal(self, ticker: str, df) -> Optional[SourceSignal]:
        last  = df.iloc[-1]
        price = self._safe(last.get("Close"))

        # Score each indicator
        scored: dict[str, tuple[str, Optional[float]]] = {}  # key → (signal, value)
        scored.update(self._score_moving_averages(last, price))
        scored.update(self._score_oscillators(last, df))
        scored.update(self._score_trend(last, price))
        scored.update(self._score_volume(df))

        # Weighted score across all indicators
        total_weight = 0.0
        raw_score    = 0.0
        for key, (sig, _) in scored.items():
            w = INDICATOR_WEIGHTS.get(key, 1.0)
            if sig != "N/A":
                raw_score    += signal_to_score(sig) * w
                total_weight += w

        score  = round(raw_score / total_weight, 4) if total_weight > 0 else 0.0
        signal = self._score_to_signal(score)

        buy_count     = sum(1 for sig, _ in scored.values() if sig == "BUY")
        sell_count    = sum(1 for sig, _ in scored.values() if sig == "SELL")
        neutral_count = sum(1 for sig, _ in scored.values() if sig in ("HOLD", "N/A"))

        # Timeframe proxy — short/medium/long trend from MAs
        timeframe_signals = self._timeframe_proxy(last, price)

        # Group into display categories
        indicators = {
            cat: [
                IndicatorValue(key=k, value=scored[k][1], signal=scored[k][0])
                for k in keys if k in scored
            ]
            for cat, keys in CATEGORIES.items()
        }

        return SourceSignal(
            source            = self.name,
            ticker            = ticker,
            timestamp         = datetime.now(),
            signal            = signal,
            score             = score,
            price             = price,
            timeframe_signals = timeframe_signals,
            indicators        = indicators,
            buy_count         = buy_count,
            sell_count        = sell_count,
            neutral_count     = neutral_count,
        )

    # ------------------------------------------------------------------
    # Category scorers
    # ------------------------------------------------------------------

    def _score_moving_averages(self, last, price) -> dict:
        out = {}
        for length, key in [(20, "SMA_20"), (50, "SMA_50"), (200, "SMA_200")]:
            col = col_sma(length)
            val = self._safe(last.get(col))
            out[key] = (score_price_vs_ma(price, val), val)
        for length, key in [(9, "EMA_9"), (21, "EMA_21")]:
            col = col_ema(length)
            val = self._safe(last.get(col))
            out[key] = (score_price_vs_ma(price, val), val)
        return out

    def _score_oscillators(self, last, df) -> dict:
        out = {}
        # RSI
        rsi_col = col_rsi(14)
        rsi_val = self._safe(last.get(rsi_col))
        out["RSI_14"] = (score_rsi(rsi_val), rsi_val)

        # MACD
        mc, ms, _ = col_macd(12, 26, 9)
        macd_val   = self._safe(last.get(mc))
        msig_val   = self._safe(last.get(ms))
        out["MACD"] = (score_macd(macd_val, msig_val), macd_val)

        # Stochastic %K
        sk, _ = col_stoch(14, 3, 3)
        stoch_val = self._safe(last.get(sk))
        out["STOCH"] = (score_stoch(stoch_val), stoch_val)

        return out

    def _score_trend(self, last, price) -> dict:
        out = {}
        # ADX
        adx_col, dmp_col, dmn_col = col_adx(14)
        adx = self._safe(last.get(adx_col))
        dmp = self._safe(last.get(dmp_col))
        dmn = self._safe(last.get(dmn_col))
        out["ADX_14"] = (score_adx(adx, dmp, dmn), adx)

        # Bollinger Bands — find columns dynamically (pandas_ta suffix varies by version)
        index = last.index if hasattr(last, "index") else []
        bbl = next((c for c in index if c.startswith("BBL_")), None)
        bbu = next((c for c in index if c.startswith("BBU_")), None)
        lower = self._safe(last.get(bbl)) if bbl else None
        upper = self._safe(last.get(bbu)) if bbu else None
        out["BBANDS"] = (score_bbands(price, lower, upper), None)

        return out

    def _score_volume(self, df) -> dict:
        obv_col = "OBV"
        if obv_col in df.columns:
            sig = score_obv(df[obv_col])
            val = self._safe(df[obv_col].iloc[-1])
        else:
            sig, val = "N/A", None
        return {"OBV": (sig, val)}

    # ------------------------------------------------------------------
    # Timeframe proxy
    # ------------------------------------------------------------------

    def _timeframe_proxy(self, last, price) -> dict[str, str]:
        """Proxy 'timeframes' from short/medium/long MA relationships."""
        ema9  = self._safe(last.get(col_ema(9)))
        ema21 = self._safe(last.get(col_ema(21)))
        sma50 = self._safe(last.get(col_sma(50)))
        sma200= self._safe(last.get(col_sma(200)))

        def _vs(a, b, label):
            if a is None or b is None:
                return "N/A"
            return "Buy" if a > b else "Sell"

        return {
            "short":  _vs(ema9, ema21, "ema9>ema21"),
            "medium": _vs(price, sma50,  "price>sma50"),
            "long":   _vs(price, sma200, "price>sma200"),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _score_to_signal(self, score: float) -> str:
        if score >= BUY_THRESHOLD:
            return "BUY"
        if score <= SELL_THRESHOLD:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _safe(value) -> Optional[float]:
        if value is None:
            return None
        try:
            import math
            f = float(value)
            return None if math.isnan(f) else round(f, 6)
        except (TypeError, ValueError):
            return None
