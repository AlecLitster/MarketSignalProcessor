"""
brokers/base.py
---------------
Abstract broker interface. Only one broker is active at a time
(ACTIVE_BROKER in settings.py). TRADING_ENABLED must be True for
any order to be placed — this is enforced in main.py before the
broker is ever called.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Position:
    ticker:   str
    quantity: float
    avg_cost: float
    market_value: Optional[float] = None


@dataclass
class Order:
    order_id:   str
    ticker:     str
    side:       str    # "BUY" | "SELL"
    quantity:   float
    order_type: str    # "MARKET" | "LIMIT"
    status:     str    # "PENDING" | "FILLED" | "CANCELLED" | "REJECTED"
    limit_price: Optional[float] = None
    filled_price: Optional[float] = None


@dataclass
class OrderResult:
    success:   bool
    order_id:  Optional[str]
    message:   str
    order:     Optional[Order] = None


class Broker(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_account_balance(self) -> Optional[float]:
        """Return available cash balance in USD."""
        ...

    @abstractmethod
    def get_position(self, ticker: str) -> Optional[Position]:
        """Return current position for ticker, or None if not held."""
        ...

    @abstractmethod
    def place_order(
        self,
        ticker:      str,
        side:        str,
        quantity:    float,
        order_type:  str = "MARKET",
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """Place an order. Returns OrderResult indicating success or failure."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    def get_open_orders(self) -> list[Order]:
        """Return all open/pending orders."""
        ...
