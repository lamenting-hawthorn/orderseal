# OrderSeal

OrderSeal is a synthetic procurement agent that separates model investigation
from the final consequential action. SQLite is authoritative, a human-only
route confirms an exact prepared cart, and uncertain acknowledgements reconcile
durable state instead of retrying blindly.

All catalogue data, users, money, addresses, and order effects are synthetic.
This repository does not connect to payments or real commerce systems.

## Current status

Phase 0 skeleton. Gate Zero passed through OpenRouter with
`openai/gpt-5.6-luna`; see `GATE_ZERO_RECEIPT.json`. The deterministic commerce
kernel is the next implementation gate.

## Setup

```bash
uv sync
uv run pytest -q
uv run uvicorn app.main:app
```

The health endpoint is `GET /health`.

Live model calls require a git-ignored `.env` containing
`ORDERSEAL_BASE_URL`, `ORDERSEAL_MODEL`, and `ORDERSEAL_API_KEY`. Never commit
or paste the key into logs, issues, or chat.

## Evidence boundary

Static code, local tests, synthetic evaluation, browser demonstration, and
deployment are distinct proof layers. Nothing here proves production payment
safety, universal model behavior, or security completeness.
