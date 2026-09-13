# Personal AI CIO — architecture

This document explains the decisions, not the file listing. Where a choice cost
more than the obvious alternative, the reason is stated; where it is a
constraint rather than a preference, that is stated too.

---

## 1. The thesis, and what follows from it

The product is not an investment-discovery app with a chatbot attached. It is a
system that continuously converts one person's financial data into a small
number of explainable decisions — and that is willing to conclude that no
decision is needed.

Three properties follow directly, and everything else in the codebase is
downstream of them:

| Property | Consequence in the code |
|---|---|
| Every number must be defensible | `aicio.engine` is a pure, network-free, LLM-free package; `aicio.provenance` makes the carrier of a value and the carrier of its history the same object |
| Every recommendation must be explainable | `Recommendation` refuses to validate without evidence, risks and counterarguments; ids are content-addressed so a decision can be re-derived |
| The product must be safe to be wrong in | Recommending and executing are separate systems; the suitability gate runs once, centrally; the grounding gate blocks a reply rather than patching it |

## 2. The pipeline

```
statements / connected accounts
        │
        ▼
  aicio.ingest        parse → exceptions the user can correct → provenance
        │
        ▼
  aicio.ingest.normalize   identifier-first merge, never name-guessing
        │
        ▼
  aicio.engine        returns · risk · allocation · x-ray · tax lots · goals
        │                          (pure functions, no clock, no network)
        ▼
  aicio.analysis      one deterministic pass → PortfolioAnalysis + FactSheet
        │
        ├────────────► aicio.decisions   rules → suitability gate → ranking
        ├────────────► aicio.alerts      dedupe · quiet hours · per-run cap
        ├────────────► aicio.reports     daily · weekly · monthly committee
        └────────────► aicio.ai          tools over the facts → grounding gate
                                                 │
                                                 ▼
                                            the user
```

`PortfolioAnalysis` is the single source of truth for one point in time. The
dashboard, the action centre, the chat and the monthly report all read from the
same object, which is why they cannot disagree about a number.

## 3. Decisions worth defending

### The engine is a purity boundary, enforced by a test

`tests/aicio/test_evals_and_purity.py` parses every module under `aicio/engine/`
and fails if it imports `urllib`, `http`, `socket`, `asyncio`, the AI layer, the
market layer or the store — or if it reads the clock. Two engine functions had
to change to satisfy it: `project_goal` and `optimise_sips` now take `today` as
a required argument rather than defaulting to `date.today()`.

That is not pedantry. "Explain the recommendation you made in March" is only
answerable if March's inputs reproduce March's output, and a hidden clock read
quietly makes that false.

### Money is Decimal; statistics are float

Currency amounts are `Decimal`, quantised to four places. Volatility, XIRR and
correlation are `float`, because they are estimates of a distribution and
Decimal would buy nothing but slowness. The boundary is one-way: money converts
to float for statistics via `as_float`, and a statistic never converts back into
a balance.

### Risk tolerance and risk capacity are separate fields

Willingness to watch a portfolio fall and ability to survive it falling are
different quantities. Policy is written to the *lower* of the two. A client who
wants aggressive equity but cannot afford a drawdown gets the portfolio they can
survive; the gap itself is disclosed, because it predicts panic-selling.

### Concentration is measured look-through, not per position

A user holding four diversified funds does not have a concentration problem,
however large each fund is as a share of the portfolio. A user with 13% in one
bank — 4% direct and 9% through three funds that all hold it — does, and no
holdings screen shows it. So `R-CONCENTRATION` fires on companies from the
X-ray, and a separate, much looser `R-POSITION-SIZE` rule covers manager risk.

Applying a 10% limit to fund positions instead would flag every sensible
five-fund portfolio and push users towards owning *more* funds that hold the
same things — the exact opposite of the intended effect.

### Redirect the next rupee before moving the last one

An 8-point equity overweight can be fixed by selling — tax, exit loads, a
decision taken away from the user — or by pointing the next several months of
contributions at what is underweight, which costs nothing. `aicio.engine.sip`
computes how long the flow-only route takes and only proposes a sale when it
cannot close the gap in a reasonable time, saying how long it would have taken
either way.

### Goals report distributions, not numbers

A single projected figure over twenty years is false precision. `project_goal`
returns percentiles and a probability, from a seeded Monte Carlo over monthly
log-normal returns. The simulation calibrates the *mean* to the stated expected
return, which means the median lands below it — volatility drag, which is real
and which a deterministic projection hides.

### DO_NOTHING is written as carefully as any other recommendation

It names what was checked, so the user can tell "we looked and it's fine" from
"we have nothing to say". The eval suite's `balanced` scenario exists to catch a
system that always finds something: a product that manufactures work is
indistinguishable from one that understands nothing.

### The AI layer cannot reach the arithmetic

The model sees a `FactSheet` and a tool surface. The tools read from an
already-computed analysis; none computes, fetches or executes anything. Every
reply then passes `aicio.ai.safety.check_grounding`, which extracts every number
in the answer and requires each to match a fact, a tool result, or an explicitly
labelled assumption. A failing reply is *replaced*, not patched — editing a
hallucinated number out of a sentence leaves the reasoning that produced it.

The offline gateway is a first-class citizen rather than a stub. With no API key
configured, the same questions are answered from the same tools in plainer
prose. That is what makes the grounding claim testable: the eval suite runs the
offline path, so a regression is a code defect rather than a prompt regression —
the only way a safety test means anything on a build with no API key.

### Cryptography is implemented here, deliberately and narrowly

The standard library has no authenticated cipher, and the PRD requires encrypted
storage for statements and forbids raw credentials reaching the model. So
`aicio.crypto` implements ChaCha20-Poly1305 from RFC 8439, verified against the
RFC's own test vectors in `tests/aicio/test_crypto.py`.

ChaCha20 rather than AES because a pure-Python AES is slower *and* more likely
to leak through cache timing; Poly1305 because an unauthenticated cipher on a
financial document is a footgun. Sealed documents and sealed tokens use
different associated data, so one cannot be substituted for the other even under
the same key. A deployment that can install `cryptography` should — this exists
so "encrypted at rest" is true out of the box rather than a to-do.

### The audit log is hash-chained

Every write commits to the hash of the row before it, so an edit or a deletion
inside the table is detectable rather than invisible. Erasure removes the user's
data and keeps the log, which holds no financial detail and is what proves the
erasure happened — that is how the right to erasure and the duty to keep records
stay compatible.

## 4. Where this diverges from the PRD's suggested stack

The PRD proposes Next.js, FastAPI, PostgreSQL, Clerk and Trigger.dev. This
implementation is standard-library Python with SQLite and a generated static
dashboard. The reasons:

* **The repository it lives in has no dependencies**, and keeping that true
  means the same checkout runs on a laptop, in a container and on a serverless
  function with nothing installed. For a financial engine that a reader must be
  able to audit line by line, that is worth more than framework ergonomics.
* **SQLite is the right size.** A person's financial record is thousands of
  rows. A single file any auditor can open with `sqlite3` beats a server they
  must be granted access to. The migrations are ordinary DDL and `Store` is the
  only class that knows about a connection, so Postgres is a contained change
  when multi-tenancy demands it.
* **The intelligence is the product.** Nothing above depends on the presentation
  stack. A Next.js front end would consume the same JSON the API already serves.

What is genuinely deferred, and should be, is in §6.

## 5. Integrations

| Connector | Kind | Status |
|---|---|---|
| Zerodha Kite | broker, IN | implemented; needs `AICIO_KITE_API_KEY` |
| Upstox | broker, IN | implemented; needs `AICIO_UPSTOX_API_KEY` |
| Angel One (SmartAPI) | broker, IN | implemented; needs `AICIO_ANGEL_API_KEY` |
| Account Aggregator (RBI) | aggregator, IN | implemented; needs a licensed AA gateway |
| Plaid | aggregator, US | implemented; needs client id and secret |
| SnapTrade | broker, US/CA | implemented; needs client id and consumer key |
| Sandbox | broker | always available; how the flow is tested and demoed |
| AMFI | NAV, IN | implemented, keyless |
| Yahoo / Finnhub / Twelve Data / Alpha Vantage | quotes | implemented behind one interface |

Every connector registers whether or not keys are present, so the connection
screen can say "Zerodha is supported and needs setup" rather than hiding it.
Consent is a first-class object with a purpose, a scope and an expiry;
requesting data without a live, in-scope consent raises rather than returning an
empty result, because an empty result looks like an empty account.

Yahoo is keyless and convenient and has no commercial redistribution licence.
That trade-off is recorded in the provider's own docstring rather than
discovered later.

## 6. What is deliberately not built

* **Execution.** Nothing here places a trade. Approving a recommendation records
  an approval. An execution integration needs its own service, its own
  permissions and its own compliance review.
* **Regulated advice.** The product is analytics with disclosures. The operating
  model — analytics/education, SEBI-registered advice, partner-led, or execution
  — has to be settled with specialist counsel before launch, and the
  recommendation language will need to follow that decision.
* **Autonomy.** Recommendation and execution permissions are separate systems by
  construction, which is the precondition for ever adding rule-bounded autonomy,
  not a substitute for it.
* **Real-time data.** AMFI publishes NAVs daily and the product says so. Nothing
  pretends to be intraday.

## 7. The eval suite as a release gate

`python -m aicio evals` runs eleven synthetic investors and the adversarial
corpus across seven properties. Four categories are critical and fail CI:
calculation, grounding, suitability and adversarial resistance. The rest report.

Failing a build on a judgement call trains people to skip the suite; failing it
on a wrong number is the entire point.

## 8. Configuration

| Variable | Purpose |
|---|---|
| `AICIO_DB` | SQLite path (default `aicio.db`) |
| `AICIO_SECRET_KEY`, `AICIO_SECRET_SALT` | document and token encryption; absent means document storage fails loudly rather than writing plaintext |
| `AICIO_API_TOKEN` | bearer token for the HTTP API; absent means open, which is correct for a local single-user run and a visible decision rather than a hidden one |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | AI banker; absent falls back to the offline gateway |
| `AICIO_LLM_PROVIDER`, `AICIO_LLM_MODEL` | override provider and model |
| `AICIO_MC_TRIALS` | simulation trials per goal in the API (default 1500) |
| `AICIO_KITE_API_KEY`, `AICIO_PLAID_CLIENT_ID`, … | per-connector credentials |
