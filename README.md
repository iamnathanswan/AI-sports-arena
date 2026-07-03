# AI Sports Arena

**Claude vs GPT vs Gemini, betting real sports markets — same bankroll, same rules, same tools. May the best model win.**

Every Monday, each AI model gets a betting session on [Kalshi](https://kalshi.com) (a CFTC-regulated prediction exchange where sports outcomes trade as binary contracts). Each agent manages its own $100 bankroll, researches the week's open markets, and places bets under identical conditions:

- **One system prompt** ([`arena/prompts/system.md`](arena/prompts/system.md)) — betting best practices: expected-value discipline, quarter-Kelly sizing, diversification, no chasing losses, honest probability forecasts.
- **One tool set** ([`arena/tools.py`](arena/tools.py)) — browse markets, check orderbooks, place bets, record reasoning. Provider adapters translate wire formats only; behavior is identical.
- **One risk layer** ([`arena/risk.py`](arena/risk.py)) — hard limits enforced in code, no matter what any model decides.

A public dashboard (GitHub Pages) tracks bankrolls, ROI, win rates, and forecast calibration (Brier scores), with every bet's reasoning on the record.

## The competitors

| Agent | Provider | Model (editable in [`config/settings.yaml`](config/settings.yaml)) |
|---|---|---|
| claude | Anthropic | `claude-opus-4-8` |
| gpt | OpenAI | `gpt-5.5` |
| gemini | Google | `gemini-3.1-pro-preview` |

## How it works

```
GitHub Actions (Mondays 16:00 UTC)
  1. settle    — resolve last week's markets, reconcile real fills, update per-agent P&L
  2. compete   — each agent runs its session (order rotates weekly), placing risk-checked bets
  3. publish   — results committed to data/, dashboard deployed to GitHub Pages
```

All agents trade through **one** Kalshi account. A virtual ledger ([`data/ledger.json`](data/ledger.json)) attributes every order to its agent and hard-blocks any agent from spending beyond its allocation.

### Safety model

| Control | Effect |
|---|---|
| `DRY_RUN` (repo variable) | **Defaults to `true`** — agents decide, everything is logged and paper-settled against real market results, but no real orders are sent. Set to `false` to go live. |
| `KILL_SWITCH` (repo variable) | `true` instantly halts all order placement (settlement still runs). |
| `KALSHI_ENV` (repo variable) | `prod` or `demo` (Kalshi's fake-money sandbox). |
| Risk limits (code-enforced) | Max 10% of equity per market · max 5 new positions/week · max 50% of equity deployed · prices 5–95c only · can never spend more cash than allocated. |

## Setup — what you need to do

1. **Kalshi account** — create one at kalshi.com, complete verification, and fund it (≥ $300 for three $100 agents). Under *Account → API Keys*, create a key: save the **key ID** and the **private key PEM file** (shown once).
2. **GitHub Actions secrets** (*Settings → Secrets and variables → Actions → Secrets*):
   - `KALSHI_API_KEY_ID` — the key ID
   - `KALSHI_PRIVATE_KEY` — the full contents of the PEM file
   - `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` — provider keys (an agent whose key is missing is skipped, so you can start with fewer)
3. **GitHub Actions variables** (same page → Variables): `DRY_RUN=true`, `KILL_SWITCH=false`, `KALSHI_ENV=prod`
4. **Enable GitHub Pages** — *Settings → Pages → Source: GitHub Actions*.
5. **Test it** — *Actions → AI Sports Arena — weekly run → Run workflow*. Watch a dry run end to end; the dashboard updates at your Pages URL.
6. **Go live** when satisfied: flip `DRY_RUN` to `false`. If you want the paper-trading results wiped so the real season starts clean, run `python -m arena.reset_season` and commit the `data/` changes first.

> The weekly cron only fires on the default branch — merge this to `main` for the schedule to activate.

### Run locally

```bash
pip install -e ".[dev]"
pytest                                  # unit tests (no network, no keys needed)
cp .env.example .env                    # fill in what you have
set -a; source .env; set +a
python -m arena.run_week                # dry-run session (needs at least one model key)
python -m http.server -d . 8000         # dashboard at http://localhost:8000/web/
```

## Fairness notes & known caveats

- Agents run **sequentially** in one workflow run, so prices can drift slightly between sessions; the run order **rotates weekly** to average this out.
- **Web search uses each provider's *native* search** (Anthropic, OpenAI, Google) — so a model researches with its own provider's engine, not a shared one. This is a deliberate tradeoff: no extra API key, but a win could partly reflect a better *search engine* rather than a better *model*. If you'd rather compare pure reasoning, swap all three to one shared search backend later (the adapters are where this lives).
- Each web search costs a little extra: Anthropic and OpenAI bill per search, and **Google bills per grounded query Gemini runs**. It's small at a weekly cadence, and it shows up in the "API cost & token usage" section along with token cost.
- Kalshi charges a small **trading fee** when an order fills (~1.75c per contract at 50c, less toward the extremes). It's deducted from each agent's cash and shown as "fees" on the leaderboard cards. The dashboard models the conservative (taker) fee, so real costs may run a touch lower.
- Two agents may take opposite sides of the same market; that's allowed (it's a model comparison, not a fund).
- Live limit orders that don't fill within 60 minutes expire and the stake **and** the fee for the unfilled portion are returned at the next settlement.
- In dry-run mode, paper bets assume a full fill at the limit price and settle against real market results.

## Responsible gambling

This is an experiment in model evaluation, not a money-making scheme or financial advice. Real-money mode risks the full bankroll of every agent — fund it only with money you are entirely comfortable losing. If gambling is a problem for you or someone close to you, call or text **1-800-GAMBLER**.
