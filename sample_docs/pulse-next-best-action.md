# Pulse — a next-best-action engine for wealth RMs

> **Every morning, the ten clients your RM should call — and why.**
> A working prototype built for the Associate Product Manager role at Ionic Wealth, aimed at the
> STORM job description line: *"an AI agent working alongside the RM"*.

An RM with 40 HNI clients can have about ten real conversations a day. Today those ten are chosen by
whoever called last. Pulse chooses them from the data: **thirteen SQL-defined signals**, each with a
rupee amount, an urgency and a conversion prior, ranked into a Morning Brief — with a Claude-written
call brief one click away, a natural-language SQL agent for the RM's own questions, and a
"what's broken" analytics page that shows the diagnosis before the cure.

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_data.py          # ~1s, deterministic synthetic book
uvicorn app.main:app --reload            # http://127.0.0.1:8000
```

Optional: `export ANTHROPIC_API_KEY=sk-ant-...` before starting to switch the call brief and
Ask STORM from template/canned mode to Claude (Opus 5 by default; see `.env.example`).

---

## What's in it

| Surface | What it does | Where |
|---|---|---|
| **Morning brief** | The RM's ranked queue: 10 of ~38 flagged clients, with ₹ in play, the "why now", the next step, and Done / Snooze / Not-relevant feedback that feeds calibration | `app/templates/brief.html` |
| **Client 360** | Allocation vs IPS, holdings, open signals with evidence, conversations, app behaviour — and the same signals rendered as client-app insight cards | `app/templates/client.html` |
| **Call brief** | Claude reads the 360 and writes 3–5 evidence-backed talking points, a WhatsApp draft in the RM's voice, likely objections, compliance checks and "don't say" phrases (structured output) | `app/ai.py` |
| **Signal explorer** | All 13 signals: trigger, ₹ rule, urgency rule, prior, RM playbook, **the SQL**, and who it flags | `app/signals/*.sql`, `app/engine.py` |
| **Book health** | Six "what's broken" findings with numbers and charts, then the measurement framework, guardrails, experiment design and rollout | `app/analytics.py` |
| **Ask STORM** | NL → SQL agent over the same DuckDB with a read-only `run_sql` tool; shows the SQL it ran. Raw SQL console too | `app/ai.py` |

## The signals

| Family | Signal | Fires when | ₹ in play |
|---|---|---|---|
| Opportunity | Liquidity event | cash up ≥ 2.5× and ≥ ₹20 L vs 3 weeks ago | the inflow |
| Opportunity | Idle cash | ≥ ₹10 L, ≥ 5% of AUM, flat for 6 weeks | the balance |
| Opportunity | Buy intent | 2+ views of one PMS/AIF/unlisted product in 10 days, not held, not discussed; suitability + ticket gates | plausible first ticket |
| Opportunity | Product closing | closing-soon product ≤ 21 days out + shown interest | minimum ticket |
| Opportunity | Lock-in / maturity | ELSS / PMS exit-load / FD maturing within 30 days | maturing value |
| Opportunity | Onboarding stuck | MF onboarding stalled 48h+ at a step | expected first ticket |
| Retention | Churn risk | withdraw screens or engagement collapse, no RM contact 3+ weeks | AUM × 30% |
| Retention | SIP at risk | failed debit / mandate expiring / SIP ending | 12 × monthly SIP |
| Portfolio | Concentration risk | one security ≥ 20% of AUM | amount above 10% |
| Portfolio | Allocation drift | invested equity ≥ 12 pts off IPS target | amount to move |
| Portfolio | Fund overlap | 4+ equity funds in one category | consolidatable value |
| Portfolio | Tax-loss harvest | material unrealised equity losses | harvestable loss |
| Relationship | Overdue review | silence beyond segment cadence | 5% of AUM |

**Expected value = ₹ in play × conversion prior × urgency**, summed per client. Priors are stated
assumptions (`app/engine.py`) until the pilot's outcomes replace them — the feedback buttons on the
Morning Brief exist for exactly that. Full logic: [docs/SIGNALS.md](docs/SIGNALS.md).

## What the data says (synthetic book: 240 clients, ₹2,150 Cr, 6 RMs)

1. **12.9% of AUM (₹277 Cr) hasn't heard from an RM in 60+ days** — 46 clients.
2. **MF onboarding completes 56% of starters; the leak is the bank e-mandate** — 27% of those who reach it stall there.
3. **₹82 Cr has sat idle for 6+ weeks across 33 clients** — ~₹3.1 Cr/yr the clients aren't earning, ~₹66 L/yr of fees the firm isn't.
4. **87% of repeat in-app product interest never becomes a logged conversation** — 33 of 38 client-product pairs.
5. **10 of 17 recent redemptions were preceded by withdraw-screen views** — 15 had no RM contact in the prior three weeks.
6. **Every RM has 2–4× more open signals than daily capacity** — prioritisation is the product, not the alert.

Numbers are from the synthetic book and exist to show the *mechanism*; the queries in `app/analytics.py`
are what I'd run on STORM's real tables in week one. Narrative: [docs/CASE_STUDY.md](docs/CASE_STUDY.md).

## Architecture

```
data/*.csv  ──▶  DuckDB (in-memory)  ──▶  app/signals/*.sql  ──▶  signals table  ──▶  Morning Brief / Client 360 / explorer
 (stand-in for            │                 (13 questions,          (scored:                    │
  STORM's warehouse)      │                  one file each)          in play × prior × urgency) │
                          └──▶  Ask STORM: Claude + run_sql tool (read-only)                    └──▶  Call brief: Claude, structured output
```

- **Python 3.12 · FastAPI · DuckDB · Jinja2 · Anthropic SDK.** No build step, no JS framework, one process.
- To plug into STORM: point `app/db.py` at the real tables (DuckDB reads Postgres / BigQuery / Parquet
  directly), keep the SQL, publish `signals` daily. The Morning Brief becomes a STORM widget; the client
  app reads the same table for insight cards.
- The generator (`scripts/generate_data.py`) plants every story at a realistic base rate — idle cash 18%,
  churn 8%, buy intent 9%, stuck onboarding 3.5% … — so the engine has true things to find and plenty
  of clients where it should stay quiet. Schema: [docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## Repo map

```
app/main.py          routes + JSON API          app/signals/*.sql   the 13 signals
app/engine.py        catalog, scoring, headlines app/analytics.py    "what's broken" queries
app/ai.py            call brief + NL→SQL agent  app/templates/      pages
app/db.py            DuckDB loader + base views  scripts/            data generator, doc builder, static build
data/                synthetic book (CSV)        docs/               case study, signals, playbook
```

## Hosted demo (no server)

`python scripts/build_static.py` writes `dist/` — every page pre-rendered, the book embedded as an
in-browser SQLite database (the SQL console and Ask STORM keep working), template briefs and prompt
contexts for all 240 clients. Published as a claude.ai Artifact, the call brief and Ask STORM run through
the viewer's own Claude account; on any other host they fall back to template briefs and canned queries.

Live: https://claude.ai/code/artifact/7983eca5-15c9-4ccc-bde6-0a57e3525d4e

## Deploy

`Dockerfile` included. Works on Render / Railway / Fly.io / Hugging Face Spaces free tiers
(set `ANTHROPIC_API_KEY` as a secret; the app runs fine without it in template mode).

## Honest limits

- Priors and thresholds are assumptions; the pilot design in Book health is how they get measured.
- Synthetic data shows mechanism, not conversion.
- Client data reaches an LLM only for the brief, with minimal context and no identifiers. Production
  would need a DPDP review, a VPC deployment and audit logging of every brief.

*Independent work. Not affiliated with or endorsed by Ionic Wealth or Angel One. Product names on the
shelf are illustrative. Nothing here is investment advice.*
