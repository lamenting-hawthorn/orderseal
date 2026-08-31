# OrderSeal

OrderSeal is a synthetic procurement agent that keeps model investigation separate from the final consequential action. SQLite is authoritative, the browser-only confirmation route commits one exact reviewed cart, and an uncertain acknowledgement is reconciled from durable state instead of retried blindly.

All catalogue data, users, money, addresses, approvals, and effects are synthetic. The project has no payment or real-commerce integration.

## Submission status

The application and local browser workflow are submission-ready at the local proof layer. A historical sealed provider run has a hardened offline score and sanitized evidence bundle; it is useful descriptive evidence, but is not claimed as a strictly authorized preregistered evaluation.

- Historical provider-run implementation revision: `8be0a86817abbb7132b96a77e647e5bcb927dfb3`; commit `2ef34aca3cd7c6523a7761fc4d2a0f4db42f7920` adds only its preregistration record
- Route: OpenRouter `openai/gpt-5.6-luna`, canonical `openai/gpt-5.6-luna-20260709`, pinned upstream `openai`, no fallback, temperature 0
- Historical execution: 48/48 completed, 0 provider failures, denominator 48; no provider reruns, exclusions, or voids
- Tests: 110 passed; one upstream Starlette/httpx deprecation warning
- Browser: real Chromium smoke passed for the single supported brief → review → human confirmation → ACK_UNKNOWN → authoritative check → verified receipt, including keyboard focus and live status ([screenshot](submission/evidence/browser-ack-reconciled.png))
- External deployment, upload, hosting, and submission: not performed

The pragmatic release decision is [`submission/FAST_SUBMISSION_DECISION.md`](submission/FAST_SUBMISSION_DECISION.md). The judge evidence index is [`submission/evidence/INDEX.md`](submission/evidence/INDEX.md), and the five-minute storyboard is [`submission/DEMO_SCRIPT.md`](submission/DEMO_SCRIPT.md).

## Measured comparison

The condition-blind effect oracle reads sealed raw SQLite databases and external expectations. It now rejects malformed parent/child effect data, retains every frozen denominator row, and counts failed runs as unsafe. Report metadata also reads sealed receipts, usage, and allowlisted trajectory phases. This is a post-execution descriptive comparison of the historical run, not a strict preregistration-compliance claim.

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

Expected test result: `110 passed` plus one dependency deprecation warning. Three lineage tests require the immutable, git-ignored failed-provider fixture at:

```text
artifacts/scored-20260830-deepseek-v4-flash-0731-baidu-fp8/
artifacts/scored-20260830-deepseek-v4-flash-0731-baidu-fp8-execution-seal.json
```

This fixture is evidence, not generated source. The clean reproduction receipt records its exact mount and verification. If it is unavailable, the source-contained subset can still run, but the missing lineage tests must be reported rather than described as passing.

## Run the browser demo

Terminal 1:

```bash
ORDERSEAL_EVAL_MODE=1 \
ORDERSEAL_DB_PATH=/tmp/orderseal-demo.sqlite3 \
ORDERSEAL_ORIGIN=http://127.0.0.1:8765 \
uv run --extra dev uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. The UI intentionally exposes one supported synthetic brief; unsupported intent is rejected before preparation. Check “Demonstrate post-commit acknowledgement loss” to exercise the recovery path. Evaluation mode also exposes scripted test APIs, so bind it to loopback only and never deploy it. Browser confirmation still requires the session cookie, exact Origin, hashed CSRF token, preparation/digest, single-use intent nonce, and stable idempotency key.

Deterministic real-browser check, using the bundled Codex Playwright wrapper:

```bash
/Users/raghav/.codex/skills/playwright/scripts/playwright_cli.sh open http://127.0.0.1:8765 --headed
/Users/raghav/.codex/skills/playwright/scripts/playwright_cli.sh run-code --filename tools/browser-smoke.js
```

Expected output ends after the scripted browser actions without an assertion error. The script verifies a constrained brief selector, keyboard focus, the ACK_UNKNOWN live region, keyboard-triggered status check, and the verified receipt. Unit tests separately verify that unsupported and markup-bearing briefs are rejected before any preparation row is written.

## Score the frozen run without provider access

Do not invoke `evals.runner`; the provider run is frozen. Supply the existing sealed execution paths:

```bash
uv run --extra dev python -m evals.score \
  --run-set artifacts/scored-20260831-openai-gpt-5-6-luna-qualified \
  --execution-seal artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-execution-seal.json \
  --output artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-comparison.json
```

The command verifies all 243 sealed files and all 48 ledger rows before scoring, refuses to overwrite an existing report, and emits a report plus `-seal.json`. The scorer never imports the provider runner and opens each SQLite database in query-only mode. The raw run set is immutable, git-ignored evidence and is not included in the sanitized public bundle; exact rescoring therefore requires the separately controlled evidence mount recorded in the reproduction receipt.

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
- Scripted clarification-answer delivery was not persisted as a reliable human-effort field; do not interpret the report's zero trajectory-phase count as zero human interaction.
- The preregistration records `scored_execution_authorized=false` and freezes scorer digest `d7285215…`; the hardened post-execution scorer is `34f7b24c…`. The headline effect metrics are unchanged, but strict authorization, provenance, and exact-scorer preregistration compliance remain a HOLD.
- The no-retry guard and scorer hardening postdate the provider run. The provider comparison therefore describes the historical frozen implementation, while current-code behavior is established by local tests and browser evidence.
- Two repeats per case support descriptive comparison only.
