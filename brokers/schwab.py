"""
brokers/schwab.py
-----------------
Charles Schwab broker scaffold.

All methods are stubbed and safe — no real orders will be placed until:
  1. TRADING_ENABLED = True in config/settings.py
  2. SCHWAB_API_KEY, SCHWAB_API_SECRET, SCHWAB_ACCOUNT_ID are in .env
  3. The stub implementations below are replaced with real Schwab API calls.

Schwab API reference: https://developer.schwab.com
OAuth2 authentication is required — implement _authenticate() first.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from brokers.base import Broker, Order, OrderResult, Position

log = logging.getLogger(__name__)

SCHWAB_API_KEY    = os.environ.get("SCHWAB_API_KEY", "")
SCHWAB_API_SECRET = os.environ.get("SCHWAB_API_SECRET", "")
SCHWAB_ACCOUNT_ID = os.environ.get("SCHWAB_ACCOUNT_ID", "")

_SCHWAB_API_BASE  = "https://api.schwabapi.com/trader/v1"


class SchwabBroker(Broker):

    @property
    def name(self) -> str:
        return "schwab"

    # ------------------------------------------------------------------
    # Authentication (implement before enabling live trading)
    # ------------------------------------------------------------------

    def _authenticate(self) -> Optional[str]:
        """
        Perform OAuth2 authentication and return an access token.
        Schwab uses OAuth2 with PKCE. See developer.schwab.com for details.

        TODO: Implement OAuth2 flow:
          1. Redirect user to authorization URL
          2. Exchange code for access + refresh tokens
          3. Store tokens securely
          4. Refresh automatically before expiry

        Returns:
            Access token string, or None if authentication fails.
        """
        log.warning("Schwab: _authenticate() is not yet implemented.")
        return None

    def _get_headers(self) -> dict:
        token = self._authenticate()
        if token is None:
            return {}
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }

    # ------------------------------------------------------------------
    # Broker interface — all stubbed
    # ------------------------------------------------------------------

    def get_account_balance(self) -> Optional[float]:
        """
        TODO: GET /accounts/{accountId}/balances
        Returns available cash in USD.
        """
        log.warning("Schwab: get_account_balance() is a stub.")
        return None

    def get_position(self, ticker: str) -> Optional[Position]:
        """
        TODO: GET /accounts/{accountId}/positions
        Filter response for matching ticker symbol.
        """
        log.warning("Schwab: get_position(%s) is a stub.", ticker)
        return None

    def place_order(
        self,
        ticker:      str,
        side:        str,
        quantity:    float,
        order_type:  str = "MARKET",
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """
        TODO: POST /accounts/{accountId}/orders
        Payload must conform to Schwab order schema.
        Always validate MAX_TRADE_SIZE_USD before calling this.
        """
        log.warning(
            "Schwab: place_order(%s %s x%.2f @ %s) is a stub — NO ORDER PLACED.",
            side, ticker, quantity, order_type,
        )
        return OrderResult(
            success  = False,
            order_id = None,
            message  = "Schwab broker is not yet implemented. Set TRADING_ENABLED=False.",
        )

    def cancel_order(self, order_id: str) -> bool:
        """
        TODO: DELETE /accounts/{accountId}/orders/{orderId}
        """
        log.warning("Schwab: cancel_order(%s) is a stub.", order_id)
        return False

    def get_open_orders(self) -> list[Order]:
        """
        TODO: GET /accounts/{accountId}/orders?status=WORKING
        """
        log.warning("Schwab: get_open_orders() is a stub.")
        return []
