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
Phase 3's evaluation foundation now includes a separate DirectBuy registry, a
query-only raw-SQLite oracle, frozen C01-C12 manifests, and a seeded 48-row AB/BA
assignment ledger. An unscored live feasibility probe made both conditions
commit once and reconcile a simulated lost acknowledgement; see
`PHASE3_FEASIBILITY_RECEIPT.json`. The candidate is not yet connected to the
model-driven case runner. Its generic server-policy path now has deterministic
coverage for clarification, comparison/no-order, landed-budget, late/missing
delivery, fallback choice, stale review, prompt-injection data, and
acknowledgement-loss reconciliation, including the composite fallback path. An
independent case-policy input manifest is now digest-bound into each generic
preparation, but it and the fair model-driven runner are not yet reviewed and
frozen, so preregistration and the 48 scored model runs remain blocked. The
offline 48-run command is harness-plumbing evidence only; its scores are not
model-performance results.

65 local tests cover the current implementation. The suite proves a functional server-rendered
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
```

Open `http://127.0.0.1:8000`. The local HTTP configuration intentionally omits
the cookie `Secure` attribute so the documented local path works. Set
`ORDERSEAL_ORIGIN` to the exact HTTPS origin in an HTTPS environment; this also
enables secure cookies. The health endpoint is `GET /health`.

Live model calls require a git-ignored `.env` containing
`ORDERSEAL_BASE_URL`, `ORDERSEAL_MODEL`, and `ORDERSEAL_API_KEY`. Never commit
or paste the key into logs, issues, or chat.

`evals/assignments.jsonl` is the planned denominator ledger. Do not edit it or
start a scored run until a reviewed `preregistration.json` exists. Every scored
timeout, provider error, crash, malformed output, and missing artifact will stay
in the denominator; selective reruns are prohibited.

## Evidence boundary

Static code, local tests, synthetic evaluation, browser demonstration, and
deployment are distinct proof layers. Nothing here proves production payment
safety, universal model behavior, or security completeness.
