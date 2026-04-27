"""
core/models.py
--------------
Central data contracts for the entire Signal Processor pipeline.

Every module speaks these types. No raw dicts are passed between stages.
If you need to add a field, add it here first — everything else follows.

Signal vocabulary
-----------------
  BUY  / SELL / HOLD        — final signal values
  OVERBOUGHT / OVERSOLD     — oscillator extreme readings
  WEAK_TREND                — ADX below threshold; direction unreliable
  N/A                       — data unavailable for this indicator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Primitive building block
# ---------------------------------------------------------------------------

@dataclass
class IndicatorValue:
    """One indicator reading with its interpreted signal."""
    key:    str
    value:  Optional[float]
    signal: str   # BUY | SELL | NEUTRAL | OVERBOUGHT | OVERSOLD | WEAK_TREND | N/A

    def as_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "signal": self.signal}


# ---------------------------------------------------------------------------
# Per-source signal
# ---------------------------------------------------------------------------

@dataclass
class SourceSignal:
    """
    Normalised output from a single signal source.

    indicators groups IndicatorValue lists by category so the dashboard
    and loggers can render them without knowing which source produced them.
    """
    source:            str         # "tradingview" | "yfinance"
    ticker:            str
    timestamp:         datetime
    signal:            str         # BUY | SELL | HOLD
    score:             float       # weighted, -1.0 → +1.0
    price:             Optional[float]
    timeframe_signals: dict[str, str]                  = field(default_factory=dict)
    indicators:        dict[str, list[IndicatorValue]] = field(default_factory=dict)
    buy_count:         int   = 0
    sell_count:        int   = 0
    neutral_count:     int   = 0
    raw:               dict  = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "source":            self.source,
            "ticker":            self.ticker,
            "timestamp":         self.timestamp.isoformat(),
            "signal":            self.signal,
            "score":             self.score,
            "price":             self.price,
            "timeframe_signals": self.timeframe_signals,
            "indicators": {
                cat: [iv.as_dict() for iv in ivs]
                for cat, ivs in self.indicators.items()
            },
            "buy_count":     self.buy_count,
            "sell_count":    self.sell_count,
            "neutral_count": self.neutral_count,
        }


# ---------------------------------------------------------------------------
# AI Synopsis — Claude's interpretation (Signal #3)
# ---------------------------------------------------------------------------

@dataclass
class AISignal:
    """
    AI-generated synopsis. Price targets only populated for BUY / SELL.
    HOLD always has None for all target fields.
    Only produced when CLAUDE_AI_SYNOPSIS_ENABLED = True.
    """
    ticker:               str
    timestamp:            datetime
    model:                str
    signal:               str            # BUY | SELL | HOLD
    confidence:           str            # HIGH | MEDIUM | LOW
    current_price:        Optional[float]
    price_target:         Optional[float] = None
    price_target_low:     Optional[float] = None
    price_target_high:    Optional[float] = None
    target_date:          Optional[str]   = None   # "YYYY-MM-DD"
    target_date_range:    Optional[str]   = None   # "YYYY-MM-DD to YYYY-MM-DD"
    reasoning:            str             = ""
    key_bullish_factors:  list[str]       = field(default_factory=list)
    key_bearish_risks:    list[str]       = field(default_factory=list)
    entry_suggestion:     Optional[str]   = None
    stop_loss_suggestion: Optional[str]   = None
    raw_response:         str             = ""

    def as_dict(self) -> dict:
        return {
            "ticker":               self.ticker,
            "timestamp":            self.timestamp.isoformat(),
            "model":                self.model,
            "signal":               self.signal,
            "confidence":           self.confidence,
            "current_price":        self.current_price,
            "price_target":         self.price_target,
            "price_target_low":     self.price_target_low,
            "price_target_high":    self.price_target_high,
            "target_date":          self.target_date,
            "target_date_range":    self.target_date_range,
            "reasoning":            self.reasoning,
            "key_bullish_factors":  self.key_bullish_factors,
            "key_bearish_risks":    self.key_bearish_risks,
            "entry_suggestion":     self.entry_suggestion,
            "stop_loss_suggestion": self.stop_loss_suggestion,
        }


# ---------------------------------------------------------------------------
# Swing event
# ---------------------------------------------------------------------------

@dataclass
class SwingEvent:
    """
    Significant change in signal or score between cycles.

    Labels are mutually exclusive, assigned in priority order:
      STRONG_SWING  — delta ≥ SWING_SCORE_STRONG_DELTA_THRESHOLD
      WEAK_SWING    — delta ≥ SWING_SCORE_WEAK_DELTA_THRESHOLD
      SCORE_SWING   — delta ≥ SWING_SCORE_DELTA_THRESHOLD
      SIGNAL_CHANGE — BUY/SELL/HOLD flipped, delta below all thresholds
    """
    ticker:          str
    timestamp:       datetime
    previous_signal: str
    current_signal:  str
    previous_score:  float
    current_score:   float
    score_delta:     float
    label:           str
    sources_changed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ticker":          self.ticker,
            "timestamp":       self.timestamp.isoformat(),
            "previous_signal": self.previous_signal,
            "current_signal":  self.current_signal,
            "previous_score":  self.previous_score,
            "current_score":   self.current_score,
            "score_delta":     self.score_delta,
            "label":           self.label,
            "sources_changed": self.sources_changed,
        }


# ---------------------------------------------------------------------------
# Cycle result — complete output for one ticker in one polling cycle
# ---------------------------------------------------------------------------

@dataclass
class CycleResult:
    """
    Everything produced for one ticker in one 15-minute cycle.
    Written to all three log types and sent to the dashboard.
    Accumulated in the per-ticker JSON history store.
    Fields are None when a source is disabled or fetch failed.
    """
    ticker:           str
    timestamp:        datetime
    tradingview:      Optional[SourceSignal] = None   # Signal #1
    yfinance:         Optional[SourceSignal] = None   # Signal #2
    ai:               Optional[AISignal]     = None   # Signal #3
    consensus_signal: str   = "HOLD"
    consensus_score:  float = 0.0
    swing_event:      Optional[SwingEvent] = None

    def as_dict(self) -> dict:
        return {
            "ticker":           self.ticker,
            "timestamp":        self.timestamp.isoformat(),
            "tradingview":      self.tradingview.as_dict() if self.tradingview else None,
            "yfinance":         self.yfinance.as_dict()    if self.yfinance    else None,
            "ai":               self.ai.as_dict()           if self.ai           else None,
            "consensus_signal": self.consensus_signal,
            "consensus_score":  self.consensus_score,
            "swing_event":      self.swing_event.as_dict()  if self.swing_event  else None,
        }

    @property
    def price(self) -> Optional[float]:
        """Best available price — prefer TradingView, then yfinance."""
        if self.tradingview and self.tradingview.price is not None:
            return self.tradingview.price
        if self.yfinance and self.yfinance.price is not None:
            return self.yfinance.price
        return None

    @property
    def has_swing(self) -> bool:
        return self.swing_event is not None

    @property
    def signal_summary(self) -> dict:
        """Flat dict for the dashboard summary table row."""
        return {
            "ticker":           self.ticker,
            "price":            self.price,
            "tv_signal":        self.tradingview.signal    if self.tradingview  else "N/A",
            "tv_score":         self.tradingview.score     if self.tradingview  else None,
            "yf_signal":        self.yfinance.signal if self.yfinance else "N/A",
            "yf_score":         self.yfinance.score  if self.yfinance else None,
            "ai_signal":        self.ai.signal             if self.ai           else "N/A",
            "ai_confidence":    self.ai.confidence         if self.ai           else "N/A",
            "ai_price_target":  self.ai.price_target       if self.ai           else None,
            "ai_target_date":   self.ai.target_date        if self.ai           else None,
            "consensus_signal": self.consensus_signal,
            "consensus_score":  self.consensus_score,
            "swing_label":      self.swing_event.label     if self.swing_event  else None,
            "timestamp":        self.timestamp.isoformat(),
        }
