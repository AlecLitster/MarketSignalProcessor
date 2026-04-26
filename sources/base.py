"""
sources/base.py
---------------
Abstract interface that every signal source must implement.

Adding a new source (e.g. Yahoo Finance, Alpha Vantage) means:
  1. Create sources/your_source.py
  2. Implement SignalSource
  3. Register it in main.py

Nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.models import SourceSignal, TrendSpotterSignal


class SignalSource(ABC):
    """Base class for all signal sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source e.g. 'tradingview'."""
        ...

    @abstractmethod
    def fetch(self, ticker: str, exchange: str) -> Optional[SourceSignal]:
        """
        Fetch and process signal data for one ticker.

        Args:
            ticker:   symbol without exchange prefix e.g. "GLD"
            exchange: exchange string e.g. "AMEX"

        Returns:
            SourceSignal on success, None on failure.
            Failures must be logged internally — never raise to the caller.
        """
        ...


class TrendSpotterSource(ABC):
    """Separate interface for TrendSpotter (BarChart proprietary signal)."""

    @abstractmethod
    def fetch_trendspotter(self, ticker: str) -> Optional[TrendSpotterSignal]:
        """
        Fetch TrendSpotter signal for one ticker.

        Returns:
            TrendSpotterSignal on success, None on failure.
        """
        ...
