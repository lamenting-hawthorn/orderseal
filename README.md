# OrderSeal

OrderSeal is a synthetic procurement agent that keeps model investigation separate from the final consequential action. SQLite is authoritative, the browser-only confirmation route commits one exact reviewed cart, and an uncertain acknowledgement is reconciled from durable state instead of retried blindly.

All catalogue data, users, money, addresses, approvals, and effects are synthetic. The project has no payment or real-commerce integration.

## Submission status

The application, frozen provider evaluation, offline score, sanitized evidence bundle, and local browser workflow are complete at the local/provider proof layers.

- Frozen execution source: `2ef34aca3cd7c6523a7761fc4d2a0f4db42f7920`
- Route: OpenRouter `openai/gpt-5.6-luna`, canonical `openai/gpt-5.6-luna-20260709`, pinned upstream `openai`, no fallback, temperature 0
- Execution: 48/48 completed, 0 provider failures, denominator 48; no reruns, exclusions, or voids
- Tests: 105 passed; one upstream Starlette/httpx deprecation warning
- Browser: real Chromium smoke passed for input → review → human confirmation → ACK_UNKNOWN → authoritative check → verified receipt, including keyboard focus, live status, and inert untrusted markup
- External deployment, upload, hosting, and submission: not performed

The judge evidence index is [`submission/evidence/INDEX.md`](submission/evidence/INDEX.md). The five-minute storyboard is [`submission/DEMO_SCRIPT.md`](submission/DEMO_SCRIPT.md).

## Measured comparison

The frozen condition-blind scorer read only sealed raw SQLite databases and external expectations.

| Condition | Safe task outcome | Case-equal macro | Duplicate | Constraint violation | Unauthorized | False success | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| DirectBuy | 12/24 (50.00%) | 50.00% | 0/24 | 0/24 | 0/24 | 0/24 | 77,319 |
| OrderSeal | 19/24 (79.17%) | 79.17% | 0/24 | 0/24 | 0/24 | 0/24 | 97,067 |

Paired OrderSeal-minus-DirectBuy mean difference: **+29.17 percentage points** across 24 pairs (9 OrderSeal-better, 13 ties, 2 DirectBuy-better). Cost is unavailable for all 48 rows and wall-clock latency was not persisted. These are descriptive synthetic results; no significance, generalization, real-payment, staging, or production claim is made.

## Install and verify

Python 3.11+ and `uv` are required.

```bash
uv sync --extra dev
uv run --extra dev ruff check .
uv run --extra dev mypy app evals tools/export_submission_evidence.py
uv run --extra dev python -m pytest -q
```

Expected test result: `105 passed` plus one dependency deprecation warning. Three lineage tests require the immutable, git-ignored failed-provider fixture at:

```text
artifacts/scored-20260830-deepseek-v4-flash-0731-baidu-fp8/
artifacts/scored-20260830-deepseek-v4-flash-0731-baidu-fp8-execution-seal.json
```

This fixture is evidence, not generated source. The clean reproduction receipt records its exact mount and verification. If it is unavailable, the other 102 source-contained tests can still run, but the missing three must be reported rather than described as passing.

## Run the browser demo

Terminal 1:

```bash
ORDERSEAL_EVAL_MODE=1 \
ORDERSEAL_DB_PATH=/tmp/orderseal-demo.sqlite3 \
ORDERSEAL_ORIGIN=http://127.0.0.1:8765 \
uv run --extra dev uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. Check “Demonstrate post-commit acknowledgement loss” to exercise the recovery path. Evaluation mode only enables the deterministic synthetic fault toggle; confirmation still requires the session cookie, exact Origin, hashed CSRF token, preparation/digest, single-use intent nonce, and stable idempotency key.

Deterministic real-browser check, using the bundled Codex Playwright wrapper:

```bash
/Users/raghav/.codex/skills/playwright/scripts/playwright_cli.sh open http://127.0.0.1:8765 --headed
/Users/raghav/.codex/skills/playwright/scripts/playwright_cli.sh run-code --filename tools/browser-smoke.js
```

Expected output ends after the scripted browser actions without an assertion error. The script verifies keyboard focus, escaped/inert untrusted markup, the ACK_UNKNOWN live region, keyboard-triggered status check, and the verified receipt.

## Score the frozen run without provider access

Do not invoke `evals.runner`; the provider run is frozen. Supply the existing sealed execution paths:

```bash
uv run --extra dev python -m evals.score \
  --run-set artifacts/scored-20260831-openai-gpt-5-6-luna-qualified \
  --execution-seal artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-execution-seal.json \
  --output artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-comparison.json
```

The command verifies all 243 sealed files and all 48 ledger rows before scoring, refuses to overwrite an existing report, and emits a report plus `-seal.json`. The scorer never imports the provider runner and opens each SQLite database in query-only mode.

## Re-export sanitized evidence

```bash
uv run --extra dev python tools/export_submission_evidence.py \
  --run-set artifacts/scored-20260831-openai-gpt-5-6-luna-qualified \
  --execution-seal artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-execution-seal.json \
  --scoring-report artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-comparison.json \
  --preregistration preregistration-luna-v1.json \
  --output submission/evidence-reproduced
```

Representative exports contain allowlisted tool name/outcome events, sanitized receipt fields, token usage, and raw-oracle output. They exclude prompts, model prose, hidden reasoning, raw provider payloads, credentials, cookies, CSRF tokens, nonces, operation keys, and session identifiers.

## Credential boundary

Live provider tooling reads `ORDERSEAL_API_KEY` from a git-ignored `.env`. Never print, inspect, log, commit, or include it in an artifact. Scoring, tests, the browser demo, and evidence export do not require the key.

## Limitations

- Synthetic SQLite effects only; no payment, identity, delivery, or real inventory integration.
- Local HTTP intentionally omits the cookie `Secure` attribute. Set an exact HTTPS `ORDERSEAL_ORIGIN` in an HTTPS environment to enable secure cookies.
- No deployed, staging, production, installed-product, or external-submission proof.
- Cost is missing for all provider rows; wall-clock latency and real human seconds were not persisted.
- Two repeats per case support descriptive comparison only.
