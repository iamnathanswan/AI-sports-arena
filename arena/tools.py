"""The shared tool registry.

Every competing model gets exactly these tools with exactly these schemas —
the provider adapters only translate the schema format, never the behavior.
Tool implementations return JSON-serializable dicts; errors come back as
{"error": "..."} strings so the model can react.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import Settings
from .fees import trading_fee_cents
from .kalshi.client import KalshiClient, KalshiError
from .ledger import Ledger
from .risk import check_order


@dataclass
class ToolContext:
    kalshi: KalshiClient
    ledger: Ledger
    settings: Settings
    agent: str
    week: str
    bets_placed: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool schemas (provider-neutral JSON Schema; adapters translate the envelope)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_bankroll",
        "description": (
            "Get your current bankroll: available cash, equity, open positions, "
            "and how much room the risk limits leave you this week. Call this first."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_sports_series",
        "description": (
            "List the sports market series currently available on the exchange "
            "(e.g. MLB game winners, WNBA games). Returns series tickers to use "
            "with list_events."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_events",
        "description": (
            "List open events (games) for a sports series, including each event's "
            "markets with current yes bid/ask prices in cents (a yes price of 55 "
            "means the market implies ~55% probability)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "series_ticker": {
                    "type": "string",
                    "description": "Series ticker from list_sports_series, e.g. KXMLBGAME",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max events to return (default 15, max 50)",
                },
            },
            "required": ["series_ticker"],
        },
    },
    {
        "name": "get_market",
        "description": (
            "Get full details for one market: rules, current yes/no bid/ask, last "
            "price, volume, open interest, and close time. Prices are in cents "
            "(1-99); buying YES at 60c pays 100c if YES resolves, 0 otherwise."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "The market ticker"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_orderbook",
        "description": "Get the current orderbook (resting bids) for a market, to judge liquidity and realistic fill prices.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "The market ticker"},
                "depth": {"type": "integer", "description": "Levels per side (default 5)"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "place_bet",
        "description": (
            "Place a limit order to BUY contracts on one side of a market. "
            "Cost = contracts x limit_price_cents, plus a small Kalshi trading fee "
            "(~0.07 x contracts x price x (1-price), highest near 50c, lowest near the "
            "extremes). Winning contracts pay 100 cents each. Every bet MUST include your "
            "probability estimate and reasoning — these are recorded and scored after the "
            "market settles. The order is checked against hard risk limits and may be rejected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "The market ticker to bet on"},
                "side": {
                    "type": "string",
                    "enum": ["yes", "no"],
                    "description": "Which side to buy",
                },
                "contracts": {
                    "type": "integer",
                    "description": "Number of contracts to buy (each pays 100c if you win)",
                },
                "limit_price_cents": {
                    "type": "integer",
                    "description": "Max price per contract in cents (1-99), for the side you chose",
                },
                "forecast_prob": {
                    "type": "number",
                    "description": (
                        "Your estimated probability (0-1) that the side you are buying wins. "
                        "Scored via Brier score after settlement — be honest and calibrated."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": "Concise reasoning for this bet (2-4 sentences); shown on the public leaderboard",
                },
            },
            "required": ["ticker", "side", "contracts", "limit_price_cents", "forecast_prob", "reasoning"],
        },
    },
    {
        "name": "record_note",
        "description": (
            "Record a note for the public log — use it to summarize your weekly strategy, "
            "or to explain why you are passing on a market or sitting the week out."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The note to record"}
            },
            "required": ["text"],
        },
    },
]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _trim_market(m: dict) -> dict:
    return {
        "ticker": m.get("ticker"),
        "title": m.get("title"),
        "subtitle": m.get("subtitle") or m.get("yes_sub_title"),
        "yes_bid": m.get("yes_bid"),
        "yes_ask": m.get("yes_ask"),
        "no_bid": m.get("no_bid"),
        "no_ask": m.get("no_ask"),
        "last_price": m.get("last_price"),
        "volume": m.get("volume"),
        "open_interest": m.get("open_interest"),
        "close_time": m.get("close_time"),
        "status": m.get("status"),
    }


def _series_allowed(ticker: str, settings: Settings) -> bool:
    allow = settings.series_allowlist
    return not allow or any(ticker.startswith(prefix) for prefix in allow)


def get_bankroll(ctx: ToolContext, args: dict) -> dict:
    limits = ctx.settings.risk
    equity = ctx.ledger.equity(ctx.agent)
    open_orders = [
        {
            "ticker": o["ticker"],
            "side": o["side"],
            "contracts": o["count"],
            "cost_cents": o["cost_cents"],
        }
        for o in ctx.ledger.open_orders(ctx.agent)
    ]
    limits_out: dict[str, Any] = {
        "min_stake_per_market_cents": limits.min_stake_cents_per_market,
        "max_stake_per_market_cents": limits.max_stake_cents_per_market,
        "max_total_deployed_cents": int(equity * limits.max_deployed_pct / 100),
        "currently_deployed_cents": ctx.ledger.open_cost(ctx.agent),
        "allowed_price_range_cents": [limits.min_price_cents, limits.max_price_cents],
    }
    # Only surface a weekly new-position budget when one is actually configured
    # (0 = unlimited).
    if limits.max_new_positions_per_week > 0:
        new_positions = ctx.ledger.new_positions_in_week(ctx.agent, ctx.week)
        limits_out["new_positions_remaining_this_week"] = max(
            limits.max_new_positions_per_week - new_positions, 0
        )
    return {
        "cash_cents": ctx.ledger.cash(ctx.agent),
        "equity_cents": equity,
        "open_positions": open_orders,
        "limits": limits_out,
    }


def list_sports_series(ctx: ToolContext, args: dict) -> dict:
    series: list[dict] = []
    for category in ctx.settings.sports_categories:
        for s in ctx.kalshi.get_series_list(category=category):
            ticker = s.get("ticker", "")
            if _series_allowed(ticker, ctx.settings):
                series.append({"ticker": ticker, "title": s.get("title")})
    return {"series": series}


def list_events(ctx: ToolContext, args: dict) -> dict:
    series_ticker = args["series_ticker"]
    if not _series_allowed(series_ticker, ctx.settings):
        return {"error": f"series {series_ticker} is not in this arena's allowlist"}
    limit = min(int(args.get("limit") or 15), 50)
    resp = ctx.kalshi.get_events(
        series_ticker=series_ticker, status="open", limit=limit, with_nested_markets=True
    )
    events = []
    for e in resp.get("events", []):
        events.append(
            {
                "event_ticker": e.get("event_ticker"),
                "title": e.get("title"),
                "markets": [_trim_market(m) for m in (e.get("markets") or [])],
            }
        )
    return {"events": events}


def get_market(ctx: ToolContext, args: dict) -> dict:
    m = ctx.kalshi.get_market(args["ticker"])
    if not m:
        return {"error": f"market {args['ticker']} not found"}
    detail = _trim_market(m)
    rules = m.get("rules_primary") or ""
    detail["rules"] = rules[:600]
    return detail


def get_orderbook(ctx: ToolContext, args: dict) -> dict:
    depth = min(int(args.get("depth") or 5), 20)
    book = ctx.kalshi.get_orderbook(args["ticker"], depth=depth)
    return {"ticker": args["ticker"], "orderbook": book}


def place_bet(ctx: ToolContext, args: dict) -> dict:
    ticker = args["ticker"]
    side = args["side"]
    count = int(args["contracts"])
    price = int(args["limit_price_cents"])
    forecast = float(args["forecast_prob"])
    reasoning = str(args["reasoning"]).strip()

    if side not in ("yes", "no"):
        return {"rejected": True, "reason": "side must be 'yes' or 'no'"}
    if not (0.0 < forecast < 1.0):
        return {"rejected": True, "reason": "forecast_prob must be strictly between 0 and 1"}
    if not reasoning:
        return {"rejected": True, "reason": "reasoning is required"}
    if not _series_allowed(ticker, ctx.settings):
        return {"rejected": True, "reason": f"{ticker} is not in this arena's allowlist"}

    fee = trading_fee_cents(count, price)
    decision = check_order(
        ctx.ledger,
        ctx.settings.risk,
        ctx.agent,
        ctx.week,
        ticker,
        count,
        price,
        kill_switch=ctx.settings.kill_switch,
        fee_cents=fee,
        forecast_prob=forecast,
    )
    if not decision:
        return {"rejected": True, "reason": decision.reason}

    # Validate the market exists and is open before committing money.
    try:
        market = ctx.kalshi.get_market(ticker)
    except KalshiError as exc:
        return {"rejected": True, "reason": f"could not fetch market: {exc}"}
    if not market:
        return {"rejected": True, "reason": f"market {ticker} not found"}
    if market.get("status") not in (None, "open", "active"):
        return {"rejected": True, "reason": f"market {ticker} is not open (status={market.get('status')})"}

    title = market.get("title") or ticker
    kalshi_order_id = None
    client_order_id = None
    initial_fill_count = 0
    status = "dry_run"

    if not ctx.settings.dry_run:
        expiration_ts = int(time.time()) + ctx.settings.risk.order_expiration_minutes * 60
        try:
            placed = ctx.kalshi.create_order(
                ticker=ticker,
                side=side,
                count=count,
                limit_price_cents=price,
                expiration_ts=expiration_ts,
            )
        except KalshiError as exc:
            return {"rejected": True, "reason": f"exchange rejected the order: {exc}"}
        kalshi_order_id = placed.get("order_id")
        client_order_id = placed.get("client_order_id")
        # Contracts that filled immediately at placement (V2 returns fill_count).
        try:
            initial_fill_count = int(float(placed.get("fill_count") or 0))
        except (TypeError, ValueError):
            initial_fill_count = 0
        status = "live"

    order = ctx.ledger.record_order(
        agent=ctx.agent,
        week=ctx.week,
        ticker=ticker,
        market_title=title,
        side=side,
        count=count,
        limit_price_cents=price,
        status=status,
        forecast_prob=forecast,
        reasoning=reasoning,
        kalshi_order_id=kalshi_order_id,
        client_order_id=client_order_id,
        fee_cents=fee,
        initial_fill_count=initial_fill_count,
    )
    ctx.bets_placed.append(order)
    return {
        "placed": True,
        "mode": status,
        "ticker": ticker,
        "side": side,
        "contracts": count,
        "limit_price_cents": price,
        "cost_cents": order["cost_cents"],
        "fee_cents": fee,
        "cash_remaining_cents": ctx.ledger.cash(ctx.agent),
        "note": (
            "DRY RUN: recorded as a paper trade, no real order sent."
            if status == "dry_run"
            else "Live limit order placed; unfilled portions are refunded at settlement."
        ),
    }


def record_note(ctx: ToolContext, args: dict) -> dict:
    text = str(args["text"]).strip()
    if not text:
        return {"error": "note text is empty"}
    ctx.ledger.record_note(ctx.agent, ctx.week, text[:2000])
    return {"recorded": True}


DISPATCH: dict[str, Callable[[ToolContext, dict], dict]] = {
    "get_bankroll": get_bankroll,
    "list_sports_series": list_sports_series,
    "list_events": list_events,
    "get_market": get_market,
    "get_orderbook": get_orderbook,
    "place_bet": place_bet,
    "record_note": record_note,
}


def execute_tool(ctx: ToolContext, name: str, args: dict) -> str:
    """Run a tool and return a JSON string result (what the model sees)."""
    fn = DISPATCH.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        result = fn(ctx, args or {})
    except KalshiError as exc:
        result = {"error": f"exchange error: {exc}"}
    except Exception as exc:  # defensive: a tool bug must not kill the whole run
        result = {"error": f"tool failed: {type(exc).__name__}: {exc}"}
    return json.dumps(result, default=str)
