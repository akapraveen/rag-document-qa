# Pulse — case study

*From "system of record" to "system of action": a next-best-action engine for STORM.*

## 1. Context

STORM is the RM platform — CRM, analytics, transactions, and an AI agent working alongside the RM.
An RM's day, as I understand it from the outside:

- A book of 30–50 HNI/UHNI families, ₹250–500 Cr under advice.
- Capacity for roughly ten meaningful conversations a day, on a good day.
- Inbound decides the day: the client who calls, the AIF that's closing, the CA who wants a statement.
- The CRM records what happened. It doesn't say what should happen next.

The constraint is not product knowledge or effort. It is **attention allocation**: 40 clients, 10 slots,
and the ten are chosen by recency of noise rather than by value or urgency.

## 2. The problem I chose

The JD says the job is to "find what's broken or underperforming, fix it, make it measurably better",
and that PMs here build before they write. So I built the thing I'd want to demo in my first month:
a Morning Brief that answers, for each RM, *who do I call today and why* — and the diagnostics that
justify it.

I chose STORM over the client app because the leverage is higher: one RM decision moves ₹ crores;
and because the same signal engine can later power the client app's insight cards, which is how I'd
extend it (see §7).

## 3. What the data says

I generated a realistic synthetic book (240 clients, ₹2,150 Cr, 6 RMs; see `docs/DATA_MODEL.md`) and
asked it the six questions I'd ask STORM's warehouse in week one. Numbers below are from that book —
they demonstrate the mechanism; the *queries* (`app/analytics.py`) are the deliverable.

| # | Finding | Number |
|---|---|---|
| 1 | AUM that hasn't heard from an RM in 60+ days | **12.9% — ₹277 Cr, 46 clients** |
| 2 | MF onboarding completion; where it leaks | **56% complete; 27% of those who reach the bank e-mandate stall there** |
| 3 | Cash idle for 6+ weeks | **₹82 Cr across 33 clients** → ~₹3.1 Cr/yr client drag, ~₹66 L/yr fee revenue |
| 4 | Repeat in-app product interest with no logged RM conversation | **87% (33 of 38 client-product pairs)** |
| 5 | Redemptions preceded by withdraw-screen views | **10 of 17 in 60 days; 15 had no RM contact in the prior 3 weeks** |
| 6 | Open signals vs daily capacity, per RM | **59–85 signals vs 10 conversations/day** |

The pattern: the data already knows. The app logs intent, the ledger shows idle money, the CRM shows
silence. None of it reaches the RM as a *decision*.

## 4. Hypothesis

> If each RM starts the day with a ranked, explained, rupee-quantified list of clients to contact,
> then coverage of at-risk AUM and conversion of observed intent will rise — because the bottleneck is
> attention allocation, not product knowledge.

Falsifiable: if RMs ignore the list (action rate < 30%) or the list's conversion is no better than the
RM's own picks (shadow-mode baseline), the hypothesis is wrong and the engine should be shut off.

## 5. What I built, and the decisions inside it

**Signals as SQL, not a model.** Thirteen questions, one file each, over the warehouse tables. Why:
explainable (an RM can argue with a threshold; nobody argues with a score), auditable (compliance can
read it), portable (it runs on STORM's Postgres/BigQuery unchanged), and fast to iterate. A model
comes later, trained on the outcomes this collects.

**Score = ₹ in play × conversion prior × urgency.** Every signal has to say how much money it is
about, how likely a conversation is to move it, and how time-bound it is. Summed per client, this gives
one number to rank on. The priors are stated assumptions (`app/engine.py`) — the product's job is to
replace them with measured rates.

**Suitability gates live in the SQL.** Buy-intent and product-closing never surface a PMS to a client
without ₹50 L of headroom or an AIF to a Conservative profile. Compliance by construction, not by RM
judgement under time pressure.

**Ten a day, not all of them.** The brief shows the top 10. Everything else is one click away. Alert
fatigue is the default failure mode of these tools; capacity is the design constraint.

**A feedback loop from day one.** Done / Snooze / Not relevant (with a reason) on every row. "Not
relevant" rates per signal type are the calibration signal: above 20%, the threshold is wrong.

**The AI writes the brief, not the decision.** Claude gets a minimal, identifier-free 360 and returns
a structured brief: talking points with evidence, a WhatsApp draft, objections, compliance checks,
phrases to avoid. The ranking stays deterministic and inspectable; the language model does what it's
good at — synthesis and tone. If the API is unavailable, a template brief renders; the RM is never
blocked.

**Ask STORM shows its SQL.** A natural-language question becomes a query through a read-only tool,
and the RM sees both the answer and the SQL — trust through transparency, and the query is reusable.

**One engine, two surfaces.** Seven of the thirteen signals have a client-facing version (idle cash,
maturity, SIP mandate, drift, overlap, concentration, tax harvest). Retention and intent signals are
RM-only. The Client 360 shows both renderings side by side.

## 6. How we'd know it works

- **North star:** incremental net flows from signal-led conversations (₹/month); AUM retained on churn
  signals as the second headline.
- **Primary:** action rate (signals acted on within 48h, target ≥ 60%); conversion rate (acted →
  outcome within 14 days).
- **Leading:** time-to-first-contact on urgency ≥ 0.8 signals (< 24h); % of AUM contacted in the
  trailing 30 days.
- **Guardrails:** opt-outs/complaints per 100 contacts; suitability exceptions (must be zero); "not
  relevant" rate per signal type (< 20%); RM time per actioned signal; redemption rate in treatment.

**Experiment.** Client-level randomisation *within* each RM's book, 50/50, six weeks. RM skill is the
largest confounder; randomising clients inside each book controls for it and gives every RM the tool.
Contamination (an RM applying a learning to a control client) biases toward the null — acceptable.
With ~240 clients the pilot is powered for large effects on flows only, so the readout leans on action
and conversion rates by signal type, and on the shadow-mode baseline.

## 7. Rollout

1. **Week 0–1, shadow mode.** Compute signals, show nobody. Measure what RMs would have done anyway.
2. **Week 2–7, pilot.** Morning Brief live for treatment clients. Weekly readout. A signal with a
   "not relevant" rate above 20% gets fixed or switched off that week.
3. **Week 8, readout and recalibration.** Priors re-fit from outcomes; thresholds tuned.
4. **Week 9+, client app.** The same `signals` table powers insight cards for self-serve segments,
   starting with idle cash and SIP mandate (lowest risk, highest volume).

## 8. Risks

- **Alert fatigue** — mitigated by the cap, the feedback loop, and killing bad signals fast.
- **RM trust** — mitigated by showing evidence and SQL, never a black-box score.
- **Data quality** — stale ledger balances or unlogged calls create false positives; the "not relevant"
  reasons make data gaps visible to leadership instead of silently eroding trust.
- **Privacy / DPDP** — client data reaches the LLM only for the brief, minimal and identifier-free;
  production needs a VPC deployment, retention controls and audit logs per brief.
- **Compliance** — no return promises anywhere in prompts or templates; suitability gates in SQL; the
  brief lists the checks the RM must do before acting.

## 9. Week one with real data

The first thing I'd do is run the six diagnostics on STORM's actual tables and see which findings hold:

- coverage gap (`interactions` × `clients` × AUM), by RM and segment;
- onboarding funnel from the app's event stream, by step and platform;
- idle balances from the ledger snapshots, with a 6-week persistence check;
- product-page views joined to CRM activity;
- redemptions joined to prior app behaviour and RM contact;
- open signals vs RM capacity.

Then pick the two signals with the clearest money and lowest false-positive risk (idle cash, SIP at
risk), ship them in shadow mode, and start the clock.

## 10. What I learned building it

- Realistic synthetic data is a product exercise in itself: deciding base rates forced me to think
  about what "normal" looks like for an HNI book before deciding what "broken" is.
- The hardest product decisions were about *silence*: when a signal should not fire (mid-onboarding,
  already discussed, unsuitable). Most of the SQL is exclusions.
- Structured output turns an LLM into a component: the UI never parses prose, and the fallback is a
  first-class path rather than an error state.
