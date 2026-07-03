"""Minimal Kalshi Trade API v2 client.

Auth model (per Kalshi docs): every authenticated request carries three headers —
  KALSHI-ACCESS-KEY:       the API key ID
  KALSHI-ACCESS-TIMESTAMP: Unix time in *milliseconds*
  KALSHI-ACCESS-SIGNATURE: base64(RSA-PSS-SHA256 signature of timestamp+METHOD+path)

The signed path includes the /trade-api/v2 prefix and excludes the query string.
Public market-data endpoints (series/events/markets/orderbook) work unsigned;
everything under /portfolio requires signing.
"""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BASE_URLS = {
    "prod": "https://api.elections.kalshi.com",
    "demo": "https://demo-api.kalshi.co",
}
API_PREFIX = "/trade-api/v2"


class KalshiError(RuntimeError):
    pass


def sign_request(private_key_pem: str, timestamp_ms: int, method: str, path: str) -> str:
    """RSA-PSS-SHA256 signature over `timestamp + METHOD + path`, base64-encoded.

    `path` must include the /trade-api/v2 prefix and exclude the query string.
    """
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    message = f"{timestamp_ms}{method.upper()}{path}".encode()
    signature = key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


class KalshiClient:
    def __init__(
        self,
        env: str = "prod",
        api_key_id: str = "",
        private_key_pem: str = "",
        min_request_interval: float = 0.15,
        timeout: float = 30.0,
    ):
        if env not in BASE_URLS:
            raise ValueError(f"KALSHI_ENV must be one of {list(BASE_URLS)}, got {env!r}")
        self.base_url = BASE_URLS[env]
        self.api_key_id = api_key_id
        self.private_key_pem = private_key_pem
        self.min_request_interval = min_request_interval
        self.timeout = timeout
        self._session = requests.Session()
        self._last_request_at = 0.0

    @property
    def can_sign(self) -> bool:
        return bool(self.api_key_id and self.private_key_pem)

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        if not self.can_sign:
            return {}
        ts = int(time.time() * 1000)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "KALSHI-ACCESS-SIGNATURE": sign_request(self.private_key_pem, ts, method, path),
        }

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth_required: bool = False,
    ) -> dict[str, Any]:
        path = API_PREFIX + endpoint
        if auth_required and not self.can_sign:
            raise KalshiError(
                f"{method} {endpoint} requires Kalshi credentials "
                "(KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY are not set)"
            )
        for attempt in range(4):
            self._throttle()
            headers = self._auth_headers(method, path)
            try:
                resp = self._session.request(
                    method,
                    self.base_url + path,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.exceptions.RequestException as exc:
                # Connection-level failure (timeout, DNS, proxy, reset). Retry a
                # few times, then surface as a KalshiError so callers (e.g.
                # settlement) can skip gracefully instead of crashing the run.
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
                raise KalshiError(f"{method} {endpoint} network error: {exc}") from exc
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
            if resp.status_code >= 400:
                raise KalshiError(f"{method} {endpoint} -> {resp.status_code}: {resp.text[:500]}")
            return resp.json() if resp.text else {}
        raise KalshiError(f"{method} {endpoint} failed after retries")

    # ----- Public market data -----

    def get_series_list(self, category: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if category:
            params["category"] = category
        return self._request("GET", "/series", params=params).get("series", [])

    def get_events(
        self,
        series_ticker: str | None = None,
        status: str = "open",
        limit: int = 100,
        with_nested_markets: bool = True,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "status": status,
            "limit": limit,
            "with_nested_markets": str(with_nested_markets).lower(),
        }
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/events", params=params)

    def get_markets(
        self,
        series_ticker: str | None = None,
        event_ticker: str | None = None,
        status: str = "open",
        limit: int = 100,
    ) -> list[dict]:
        params: dict[str, Any] = {"status": status, "limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        return self._request("GET", "/markets", params=params).get("markets", [])

    def get_market(self, ticker: str) -> dict:
        return self._request("GET", f"/markets/{ticker}").get("market", {})

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return self._request(
            "GET", f"/markets/{ticker}/orderbook", params={"depth": depth}
        ).get("orderbook", {})

    # ----- Portfolio (signed) -----

    def get_balance(self) -> dict:
        return self._request("GET", "/portfolio/balance", auth_required=True)

    def get_positions(self, ticker: str | None = None) -> dict:
        params = {"ticker": ticker} if ticker else None
        return self._request("GET", "/portfolio/positions", params=params, auth_required=True)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/portfolio/orders/{order_id}", auth_required=True).get(
            "order", {}
        )

    def get_fills(self, ticker: str | None = None, limit: int = 200) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return self._request("GET", "/portfolio/fills", params=params, auth_required=True).get(
            "fills", []
        )

    def get_settlements(self, limit: int = 200) -> list[dict]:
        return self._request(
            "GET", "/portfolio/settlements", params={"limit": limit}, auth_required=True
        ).get("settlements", [])

    def create_order(
        self,
        ticker: str,
        side: str,  # "yes" | "no"
        count: int,
        limit_price_cents: int,
        action: str = "buy",
        expiration_ts: int | None = None,
        client_order_id: str | None = None,
    ) -> dict:
        """Place a limit order to buy `count` contracts of `side` at
        `limit_price_cents` (1-99).

        Uses the V2 order-write surface (POST /portfolio/events/orders). The
        legacy POST /portfolio/orders endpoint this previously called returns
        410 deprecated_v1_order_endpoint -- Kalshi has retired it in favor of
        a unified bid/ask book with dollar-denominated prices. `action` is
        accepted for backwards compatibility with callers but unused: V2's
        create endpoint only opens positions (no separate buy/sell action);
        closing/reducing a position would go through a different endpoint
        (decrease_v2), which this client does not implement.
        """
        body: dict[str, Any] = {
            "ticker": ticker,
            "client_order_id": client_order_id or str(uuid.uuid4()),
            # V2 collapses the old side="yes"/"no" + yes_price/no_price pair
            # into one book-side field: "bid" is the yes side, "ask" is the
            # no side, each priced in its own dollar terms (same semantics as
            # the old yes_price/no_price, just renamed and in dollars).
            "side": "bid" if side == "yes" else "ask",
            # V2's Go struct wants count as a numeric string, not a JSON
            # number -- sending an int here 400s with "cannot unmarshal
            # number into Go struct field CreateOrderV2Request.count of
            # type string". Same fixed-point-string convention as price.
            "count": str(count),
            "price": f"{limit_price_cents / 100:.4f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
        }
        if expiration_ts is not None:
            body["expiration_time"] = expiration_ts
        return self._request(
            "POST", "/portfolio/events/orders", json_body=body, auth_required=True
        ).get("order", {})
