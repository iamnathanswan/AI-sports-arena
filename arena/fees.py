"""Kalshi trading fees.

Kalshi charges a trading fee when an order fills (settlement itself is free).
The general/sports taker fee is:

    fee = roundup_to_cent( 0.07 * contracts * price * (1 - price) )

with price in dollars (0.01-0.99). The fee peaks near 50c (~1.75c/contract)
and shrinks toward the extremes -- the exchange rewards conviction. Maker
fills (resting orders that get hit) are charged 25% of that, and round to
$0 for most small orders.

We model the *taker* fee by default: it's the higher of the two, so the
dashboard errs toward slightly overstating cost rather than flattering an
agent's P&L. In live mode the true fee comes from Kalshi's fill records and
may be a touch lower for maker fills; this is a deliberately conservative
estimate, not an exact reconciliation.
"""

from __future__ import annotations

import math

# General/sports fee coefficient from Kalshi's published schedule (checked
# 2026-07-02). A few non-sports series use different rates; edit here if you
# add those.
TAKER_COEFFICIENT = 0.07
MAKER_MULTIPLIER = 0.25


def trading_fee_cents(count: int, price_cents: int, maker: bool = False) -> int:
    """Estimated Kalshi trading fee in whole cents for `count` contracts filled
    at `price_cents` (1-99). Rounded up to the next cent, per Kalshi."""
    if count <= 0 or not (0 < price_cents < 100):
        return 0
    coefficient = TAKER_COEFFICIENT * (MAKER_MULTIPLIER if maker else 1.0)
    # fee_dollars = coeff * count * P * (1-P), P = price_cents/100
    # -> in cents: coeff * count * price_cents * (100 - price_cents) / 10000 * 100
    fee_cents_exact = coefficient * count * price_cents * (100 - price_cents) / 100
    return math.ceil(fee_cents_exact)
