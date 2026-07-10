# AI Sports Arena

**Claude vs GPT vs Gemini, betting real sports markets — same bankroll, same rules, same tools. May the best model win.**

Every day, each AI model gets a betting session on [Kalshi](https://kalshi.com) (a CFTC-regulated prediction exchange where sports outcomes trade as binary contracts). Each agent manages its own $100 bankroll, hunts for a **news-driven mispricing** in that day's games, and places bets under identical conditions:

- **One system prompt** ([`arena/prompts/system.md`](arena/prompts/system.md)) — a news-first strategy: find fresh, decision-relevant news (lineups, injuries, pitchers, weather) the market hasn't priced yet, and **deploy at least $20 per run** into the best positive-edge mispricings (quarter-Kelly sizing, highest edge funded first). Every bet must clear the price *and* the fee — it never places a bet it expects to lose.
- **One tool set** ([`arena/tools.py`](arena/tools.py)) — browse markets, check orderbooks, place bets, record reasoning. Provider adapters translate wire formats only; behavior is identical.
- **One risk layer** ([`arena/risk.py`](arena/risk.py)) — hard limits enforced in code, including a **net-EV gate** that rejects any bet whose stated edge doesn't beat the price and fee by a margin. No matter what any model decides.

### Strategy: why news, and why not speed

Viral stories of AI bots making fortunes on prediction markets come from two very different tactics. One is **latency arbitrage** — reacting to the pricing engine in milliseconds — which is pure high-frequency trading; a scheduled bot cannot and should not compete there. The other is **news repricing** — estimating how breaking news moves a probability and trading before the market catches up — which is exactly what a strong reasoning model *can* do. This arena commits to the second: it runs daily near game time, leans on each model's judgment over fresh news in softer/lower-liquidity markets, and refuses fair-value bets that only feed the fee. (Reality check: most prediction-market wallets lose money and the success stories are heavily survivorship-biased — the goal here is a disciplined, positive-EV process, not a get-rich screenshot.)

A public dashboard (GitHub Pages) tracks bankrolls, ROI, win rates, and forecast calibration (Brier scores), with every bet's reasoning on the record.

## The competitors

| Agent | Provider | Model (editable in [`config/settings.yaml`](config/settings.yaml)) |
|---|---|---|
| claude | Anthropic | `claude-opus-4-8` |
| gpt | OpenAI | `gpt-5.5` |
| gemini | Google | `gemini-3.1-pro-preview` |

## How it works

```
GitHub Actions (daily, 21:00 UTC — ~5pm ET, after lineups are out)
  1. settle    — resolve finished markets, reconcile real fills, update per-agent P&L
  2. compete   — each agent runs its session (order rotates daily), placing risk-checked
                 bets only where a news-driven edge clears the net-EV gate (or passing)
  3. publish   — results committed to data/, dashboard deployed to GitHub Pages
```

All agents trade through **one** Kalshi account. A virtual ledger ([`data/ledger.json`](data/ledger.json)) attributes every order to its agent and hard-blocks any agent from spending beyond its allocation.

### Safety model

| Control | Effect |
|---|---|
| `DRY_RUN` (repo variable) | **Defaults to `true`** — agents decide, everything is logged and paper-settled against real market results, but no real orders are sent. Set to `false` to go live. |
| `KILL_SWITCH` (repo variable) | `true` instantly halts all order placement (settlement still runs). |
| `KALSHI_ENV` (repo variable) | `prod` or `demo` (Kalshi's fake-money sandbox). |
| Risk limits (code-enforced) | ≥$20 deployed per run · positive net edge after price + fee (no bet it expects to lose) · $10–$20 staked per market · max 50% of equity deployed · prices 5–95c only · can never spend more cash than allocated. |

## Setup — what you need to do

1. **Kalshi account** — create one at kalshi.com, complete verification, and fund it (≥ $300 for three $100 agents). Under *Account → API Keys*, create a key: save the **key ID** and the **private key PEM file** (shown once).
2. **GitHub Actions secrets** (*Settings → Secrets and variables → Actions → Secrets*):
   - `KALSHI_API_KEY_ID` — the key ID
   - `KALSHI_PRIVATE_KEY` — the full contents of the PEM file
   - `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` — provider keys (an agent whose key is missing is skipped, so you can start with fewer)
3. **GitHub Actions variables** (same page → Variables): `DRY_RUN=true`, `KILL_SWITCH=false`, `KALSHI_ENV=prod`
4. **Enable GitHub Pages** — *Settings → Pages → Source: GitHub Actions*.
5. **Test it** — *Actions → AI Sports Arena — daily run → Run workflow*. Watch a dry run end to end; the dashboard updates at your Pages URL.
6. **Go live** when satisfied: flip `DRY_RUN` to `false`. If you want the paper-trading results wiped so the real season starts clean, run `python -m arena.reset_season` and commit the `data/` changes first.

> The daily cron only fires on the default branch — merge this to `main` for the schedule to activate.

### Run locally

```bash
pip install -e ".[dev]"
pytest                                  # unit tests (no network, no keys needed)
cp .env.example .env                    # fill in what you have
set -a; source .env; set +a
python -m arena.run_week                # dry-run session (needs at least one model key)
python -m http.server -d . 8000         # dashboard at http://localhost:8000/web/
```

## Controlling API cost

Running three frontier models **daily** costs real money — roughly 7× a weekly cadence — and web search adds to it. Every lever below lives in [`config/settings.yaml`](config/settings.yaml) and applies **identically to every agent** (so the comparison stays fair). Watch the **"API cost & token usage"** section of the dashboard to see the effect. (Note: `min_deploy_cents_per_run` requires each agent to stake at least $20/run, so it *will* place bets daily — set it to `0` if you'd rather agents pass on flat days.)

| Lever | Setting | What it does |
|---|---|---|
| **Reasoning effort** | `effort: medium` | The biggest dial. Models "think" less at lower effort — and thinking tokens bill at the expensive output rate. `medium` keeps analysis strong at roughly half the thinking spend of `high`; drop to `low` to cut further. |
| **Search cap** | `max_searches_per_session: 5` | Caps native web searches per session (hard on Anthropic, prompted on the others). Five good searches covers a slate; uncapped search is what balloons the resent context. |
| **Per-session cost ceiling** | `max_cost_cents_per_session: 100` | A hard backstop: a session that reaches $1.00 of estimated spend stops. It's a runaway guard, not a tight leash — **tune it down once you've seen real per-session costs on the dashboard**. Set `0` to disable. |
| **Turn cap** | `max_turns: 25` | Bounds worst-case loops. |
| **Fewer / cheaper models** | `agents:` list | Drop an agent, or swap a premium model for a cheaper tier (e.g. a Sonnet/Flash "control"). Each agent's per-token prices are set right there too. |

One efficiency win is built in and needs no configuration: the shared system prompt + tools are **prompt-cached** (cache reads are ~10% of input price — watch the "Cache read" column to confirm it's landing).

## Fairness notes & known caveats

- Agents run **sequentially** in one workflow run, so prices can drift slightly between sessions; the run order **rotates daily** to average this out.
- **Web search uses each provider's *native* search** (Anthropic, OpenAI, Google) — so a model researches with its own provider's engine, not a shared one. This is a deliberate tradeoff: no extra API key, but a win could partly reflect a better *search engine* rather than a better *model*. If you'd rather compare pure reasoning, swap all three to one shared search backend later (the adapters are where this lives).
- Each web search costs a little extra: Anthropic and OpenAI bill per search, and **Google bills per grounded query Gemini runs**. At a daily cadence this adds up — budget accordingly and watch the "API cost & token usage" section, which includes it alongside token cost.
- Kalshi charges a small **trading fee** when an order fills (~1.75c per contract at 50c, less toward the extremes). It's deducted from each agent's cash and shown as "fees" on the leaderboard cards. The dashboard models the conservative (taker) fee, so real costs may run a touch lower.
- Two agents may take opposite sides of the same market; that's allowed (it's a model comparison, not a fund).
- Live limit orders that don't fill within 60 minutes expire and the stake **and** the fee for the unfilled portion are returned at the next settlement.
- In dry-run mode, paper bets assume a full fill at the limit price and settle against real market results.

## Responsible gambling

This is an experiment in model evaluation, not a money-making scheme or financial advice. Real-money mode risks the full bankroll of every agent — fund it only with money you are entirely comfortable losing. If gambling is a problem for you or someone close to you, call or text **1-800-GAMBLER**.
