"""
ai/base.py
----------
Abstract interface for AI interpretation models.

Adding a new AI model (GPT-4, Gemini, etc.) means:
  1. Create ai/your_model.py
  2. Implement AIInterpreter
  3. Register it in main.py if CLAUDE_AI_SYNOPSIS_ENABLED is False
     and you want a different model active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.models import AISignal, CycleResult


class AIInterpreter(ABC):

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier string e.g. 'claude-sonnet-4-20250514'."""
        ...

    @abstractmethod
    def interpret(
        self,
        result: CycleResult,
        history: list[dict],
    ) -> Optional[AISignal]:
        """
        Generate an AI synopsis for one ticker.

        Args:
            result:  the current CycleResult (all four signals for this cycle).
            history: list of past CycleResult.as_dict() entries for this ticker,
                     ordered oldest → newest (from ticker JSON store).
                     Length determined by AI_HISTORY_CYCLES in settings.

        Returns:
            AISignal on success, None on failure or if confidence is too low.
            Failures must be logged internally — never raise to the caller.

        Contract:
            - HOLD signals must have None for all price target fields.
            - LOW confidence signals must return signal="HOLD" regardless of
              the model's directional assessment.
        """
        ...
