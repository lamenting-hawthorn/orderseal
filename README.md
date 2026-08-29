# OrderSeal

OrderSeal is a synthetic procurement agent that separates model investigation
from the final consequential action. SQLite is authoritative, a browser-only
capability route confirms an exact prepared cart, and uncertain acknowledgements
reconcile durable state instead of retrying blindly.

All catalogue data, users, money, addresses, and order effects are synthetic.
This repository does not connect to payments or real commerce systems.

## Current status

Phase 1 bounded-effect slice accepted by an independent local veto review.
Phase 2's seven-tool static investigation registry passed an independent local
veto review. One authorized live exact-SKU run reached
`ready_for_confirmation` without exposing a confirmation capability; see
`PHASE2_LIVE_RECEIPT.json`.
Gate Zero passed through OpenRouter with
`openai/gpt-5.6-luna`; see `GATE_ZERO_RECEIPT.json`. The local public-route
41 local tests cover both phases. The suite proves a functional server-rendered
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
```

Open `http://127.0.0.1:8000`. The local HTTP configuration intentionally omits
the cookie `Secure` attribute so the documented local path works. Set
`ORDERSEAL_ORIGIN` to the exact HTTPS origin in an HTTPS environment; this also
enables secure cookies. The health endpoint is `GET /health`.

Live model calls require a git-ignored `.env` containing
`ORDERSEAL_BASE_URL`, `ORDERSEAL_MODEL`, and `ORDERSEAL_API_KEY`. Never commit
or paste the key into logs, issues, or chat.

## Evidence boundary

Static code, local tests, synthetic evaluation, browser demonstration, and
deployment are distinct proof layers. Nothing here proves production payment
safety, universal model behavior, or security completeness.
