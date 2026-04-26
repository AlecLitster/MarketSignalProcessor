"""
ai/claude.py
------------
Claude (Anthropic) AI interpreter implementation.

Claude receives the full per-ticker history log as context — not just the
current cycle — so it can reason about trend direction, momentum, and
whether signals are strengthening or fading.

The prompt enforces a strict JSON response schema. Claude is instructed to:
  - Only assign BUY or SELL when confidence is HIGH or MEDIUM.
  - Always return HOLD (with no price targets) when confidence is LOW.
  - Never return price targets for HOLD signals.
  - Provide price target ranges and date ranges for BUY/SELL signals.
  - Focus analysis on strong buy/sell setups with specific entry,
    target, and stop-loss levels.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from config.settings import (
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    CLAUDE_TIMEOUT_SECONDS,
    CLAUDE_MAX_RETRIES,
    AI_HISTORY_CYCLES,
)
from core.models import AISignal, CycleResult
from ai.base import AIInterpreter

log = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"

_SYSTEM_PROMPT = """You are an expert quantitative financial analyst specialising in technical analysis.

You will receive multi-source technical signal data for a stock or ETF, including history across multiple polling cycles. Your task is to synthesise all signals into a single high-quality investment assessment.

CRITICAL RULES:
1. Only assign BUY or SELL when your confidence is HIGH or MEDIUM.
2. When confidence is LOW, always return signal = "HOLD" regardless of direction.
3. HOLD signals must have null for ALL price target and date fields.
4. BUY and SELL signals must include price_target, price_target_low, price_target_high, target_date, and target_date_range.
5. Price targets must be realistic given current price and technical levels (support/resistance, pivot points).
6. Focus on HIGH-conviction setups. Weak or conflicting signals should result in HOLD.
7. Consider signal consistency across multiple cycles — a single-cycle spike is less reliable than sustained signals.

You must respond with ONLY a valid JSON object — no preamble, no markdown, no explanation outside the JSON.

JSON Schema:
{
  "ticker": "string",
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "current_price": number | null,
  "price_target": number | null,
  "price_target_low": number | null,
  "price_target_high": number | null,
  "target_date": "YYYY-MM-DD" | null,
  "target_date_range": "YYYY-MM-DD to YYYY-MM-DD" | null,
  "reasoning": "string — concise 2-3 sentence synthesis",
  "key_bullish_factors": ["string", ...],
  "key_bearish_risks": ["string", ...],
  "entry_suggestion": "string | null",
  "stop_loss_suggestion": "string | null"
}"""


class ClaudeInterpreter(AIInterpreter):

    @property
    def model_name(self) -> str:
        return CLAUDE_MODEL

    def interpret(
        self,
        result: CycleResult,
        history: list[dict],
    ) -> Optional[AISignal]:
        """Generate AI synopsis using Claude."""
        if not CLAUDE_API_KEY:
            log.error("CLAUDE_API_KEY not set — cannot generate AI synopsis")
            return None

        prompt  = self._build_prompt(result, history)
        raw     = self._call_claude(prompt)
        if raw is None:
            return None

        return self._parse_response(raw, result)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, result: CycleResult, history: list[dict]) -> str:
        """Build a rich, structured prompt with all signal context."""
        lines = [
            f"# Signal Analysis Request: {result.ticker}",
            f"Timestamp: {result.timestamp.isoformat()}",
            f"Current Price: {result.price or 'Unknown'}",
            "",
            "## Current Cycle — Consensus",
            f"  Signal : {result.consensus_signal}",
            f"  Score  : {result.consensus_score:+.4f}  (range: -1.0 → +1.0)",
            "",
        ]

        # TradingView signal
        if result.tradingview:
            tv = result.tradingview
            lines += [
                "## Signal #1 — TradingView",
                f"  Signal : {tv.signal}  |  Score: {tv.score:+.4f}",
                "  Timeframes:",
            ]
            for tf, sig in tv.timeframe_signals.items():
                lines.append(f"    {tf:<10}: {sig}")
            lines += ["  Key Indicators:"]
            for cat, ivs in tv.indicators.items():
                if cat == "pivots":
                    continue
                for iv in ivs:
                    if iv.signal not in ("N/A",) and iv.value is not None:
                        lines.append(f"    {iv.key:<22}: {iv.value:.4f}  [{iv.signal}]")
            # Pivot levels for context
            pivot_ivs = tv.indicators.get("pivots", [])
            if pivot_ivs:
                lines.append("  Pivot Levels:")
                for iv in pivot_ivs:
                    if iv.value is not None:
                        lines.append(f"    {iv.key:<30}: {iv.value:.2f}")
            lines.append("")

        # BarChart signal
        if result.barchart:
            bc = result.barchart
            lines += [
                "## Signal #2 — BarChart",
                f"  Signal : {bc.signal}  |  Score: {bc.score:+.4f}",
                "  Timeframes:",
            ]
            for tf, sig in bc.timeframe_signals.items():
                lines.append(f"    {tf:<10}: {sig}")
            lines += ["  Key Indicators:"]
            for cat, ivs in bc.indicators.items():
                if cat == "price_volume":
                    continue
                for iv in ivs:
                    if iv.signal not in ("N/A",) and iv.value is not None:
                        lines.append(f"    {iv.key:<22}: {iv.value:.4f}  [{iv.signal}]")
            lines.append("")

        # TrendSpotter
        if result.trendspotter:
            ts = result.trendspotter
            lines += [
                "## Signal #3 — BarChart TrendSpotter",
                f"  Signal   : {ts.signal}",
                f"  Strength : {ts.strength}",
                f"  Change   : {ts.change}",
                f"  Score    : {ts.score:+.4f}",
            ]
            if ts.signal_date:
                lines.append(f"  Since    : {ts.signal_date} ({ts.days_in_signal or '?'} trading days)")
            lines.append("")

        # Swing event context
        if result.swing_event:
            sw = result.swing_event
            lines += [
                "## Swing Alert",
                f"  Label    : {sw.label}",
                f"  Previous : {sw.previous_signal}  (avg score {sw.previous_score:+.4f})",
                f"  Current  : {sw.current_signal}   (score {sw.current_score:+.4f})",
                f"  Delta    : {sw.score_delta:+.4f}",
                f"  Driven by: {', '.join(sw.sources_changed) or 'multiple sources'}",
                "",
            ]

        # Historical context
        recent_history = history[-(AI_HISTORY_CYCLES):]
        if recent_history:
            lines += [
                f"## Signal History (last {len(recent_history)} cycles)",
                f"  {'Timestamp':<22} {'Consensus':<8} {'Score':>8}  {'TV':<6} {'BC':<6} {'TS':<6}",
                f"  {'-'*65}",
            ]
            for entry in recent_history:
                ts_str  = entry.get("timestamp", "")[:19]
                cons    = entry.get("consensus_signal", "N/A")
                score   = entry.get("consensus_score", 0.0)
                tv_sig  = (entry.get("tradingview") or {}).get("signal", "N/A")
                bc_sig  = (entry.get("barchart")    or {}).get("signal", "N/A")
                ts_sig  = (entry.get("trendspotter") or {}).get("signal", "N/A")
                lines.append(
                    f"  {ts_str:<22} {cons:<8} {score:>+8.4f}  {tv_sig:<6} {bc_sig:<6} {ts_sig:<6}"
                )
            lines.append("")

        lines += [
            "## Instructions",
            "Synthesise all signals above into a single JSON response.",
            "Apply the CRITICAL RULES from your system prompt.",
            "Be specific about price targets — use pivot levels and MA values as anchors.",
            "Today's date for target date estimation: " + datetime.now().strftime("%Y-%m-%d"),
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    def _call_claude(self, prompt: str) -> Optional[str]:
        """Call Claude API with retry. Returns raw response text or None."""
        headers = {
            "x-api-key":         CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        payload = {
            "model":      CLAUDE_MODEL,
            "max_tokens": CLAUDE_MAX_TOKENS,
            "system":     _SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": prompt}],
        }

        for attempt in range(1, CLAUDE_MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    _API_URL,
                    headers=headers,
                    json=payload,
                    timeout=CLAUDE_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                data    = resp.json()
                content = data.get("content", [])
                text    = " ".join(
                    block.get("text", "") for block in content if block.get("type") == "text"
                )
                return text.strip()

            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    wait = 2 ** attempt
                    log.warning("Claude rate-limited. Waiting %ds (attempt %d/%d)", wait, attempt, CLAUDE_MAX_RETRIES)
                    time.sleep(wait)
                else:
                    log.error("Claude API HTTP error: %s", exc)
                    return None
            except Exception as exc:
                log.error("Claude API error attempt %d/%d: %s", attempt, CLAUDE_MAX_RETRIES, exc)
                if attempt < CLAUDE_MAX_RETRIES:
                    time.sleep(2 ** attempt)

        return None

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str, result: CycleResult) -> Optional[AISignal]:
        """Parse Claude's JSON response into an AISignal."""
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            log.error("Claude response not valid JSON for %s: %s\nRaw: %s", result.ticker, exc, raw[:500])
            return None

        signal     = data.get("signal", "HOLD").upper()
        confidence = data.get("confidence", "LOW").upper()

        # Enforce: LOW confidence → HOLD, no targets
        if confidence == "LOW":
            signal = "HOLD"

        # Enforce: HOLD → no price targets
        price_target      = None
        price_target_low  = None
        price_target_high = None
        target_date       = None
        target_date_range = None

        if signal in ("BUY", "SELL"):
            price_target      = self._safe_float(data.get("price_target"))
            price_target_low  = self._safe_float(data.get("price_target_low"))
            price_target_high = self._safe_float(data.get("price_target_high"))
            target_date       = data.get("target_date")
            target_date_range = data.get("target_date_range")

        return AISignal(
            ticker               = result.ticker,
            timestamp            = result.timestamp,
            model                = self.model_name,
            signal               = signal,
            confidence           = confidence,
            current_price        = self._safe_float(data.get("current_price")) or result.price,
            price_target         = price_target,
            price_target_low     = price_target_low,
            price_target_high    = price_target_high,
            target_date          = target_date,
            target_date_range    = target_date_range,
            reasoning            = data.get("reasoning", ""),
            key_bullish_factors  = data.get("key_bullish_factors", []),
            key_bearish_risks    = data.get("key_bearish_risks", []),
            entry_suggestion     = data.get("entry_suggestion"),
            stop_loss_suggestion = data.get("stop_loss_suggestion"),
            raw_response         = raw,
        )

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None
