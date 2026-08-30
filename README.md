# OrderSeal

OrderSeal is a synthetic procurement agent that separates model investigation
from the final consequential action. SQLite is authoritative, a browser-only
capability route confirms an exact prepared cart, and uncertain acknowledgements
reconcile durable state instead of retrying blindly.

All catalogue data, users, money, addresses, and order effects are synthetic.
This repository does not connect to payments or real commerce systems.

## Current status

Phase 1 bounded-effect slice and Phase 2's seven-tool investigation registry
passed independent local veto reviews. One authorized live exact-SKU run reached
`ready_for_confirmation` without exposing a confirmation capability; see
`PHASE2_LIVE_RECEIPT.json`.
Gate Zero passed through OpenRouter with
`openai/gpt-5.6-luna`; see `GATE_ZERO_RECEIPT.json`. The local public-route
Phase 3 now includes separate OrderSeal and DirectBuy registries, independent
case-policy inputs, a query-only raw-SQLite scorer, frozen C01-C12 manifests, and
a seeded 48-row AB/BA assignment ledger. The oracle-blind paired provider runner
uses a fresh database and aggregate budget per assignment, binds equal pair
parameters, retains every failure in the denominator without retry, records a
strict model-produced claim separately from SQLite evidence, and fails closed on
model drift. DirectBuy now receives the same request, landed pricing, policy,
approval, mutation, provider route, and fault schedule while retaining its
conventional direct-action boundary. A fresh independent veto passed this
bounded runner slice. No C01-C12 provider or scored run has been executed.

79 local tests cover the current implementation. The suite proves a functional server-rendered
confirmation, provenance that labels
the browser operator as unverified rather than asserting human identity, one
atomic stock/order effect,
post-commit acknowledgement-loss recording, reconciliation, replay safety,
stale-quote rejection, exact-boundary expiry, delayed-lock expiry, and
cross-session isolation.

## Setup

```bash
uv sync
uv run pytest -q
uv run python -m app.db reset --path orderseal.db --seed orderseal-v1
uv run uvicorn app.main:app
uv run python live_agent_probe.py
uv run python phase3_feasibility_probe.py
uv run python -m evals.run --simulated --output artifacts/<new-run-set>
uv run python -m evals.preregister
```

Open `http://127.0.0.1:8000`. The local HTTP configuration intentionally omits
the cookie `Secure` attribute so the documented local path works. Set
`ORDERSEAL_ORIGIN` to the exact HTTPS origin in an HTTPS environment; this also
enables secure cookies. The health endpoint is `GET /health`.

The browser probes use a git-ignored `.env` containing
`ORDERSEAL_BASE_URL`, `ORDERSEAL_MODEL`, and `ORDERSEAL_API_KEY`. Never commit
or paste the key into logs, issues, or chat.

The scored runner reads `ORDERSEAL_API_KEY`; any supplied base URL and model must
exactly match the source freeze. The current OpenRouter contract is
`deepseek/deepseek-v4-flash-0731`, canonical model
`deepseek/deepseek-v4-flash-20260731`, upstream provider `deepseek`, no provider
fallback, and temperature zero. An authenticated metadata preflight must pass
before any output directory is created. Do not invoke `python -m evals.runner`
until `preregistration-deepseek-v1.json` has been reviewed and the project owner
separately authorizes the full 48-row run.

`evals/assignments.jsonl` is the sole denominator ledger. Do not edit it after
the immutable preregistration freeze. Every scored
timeout, provider error, crash, malformed output, and missing artifact will stay
in the denominator; selective reruns are prohibited.

## Evidence boundary

Static code, local tests, synthetic evaluation, browser demonstration, and
deployment are distinct proof layers. Nothing here proves production payment
safety, universal model behavior, or security completeness.
