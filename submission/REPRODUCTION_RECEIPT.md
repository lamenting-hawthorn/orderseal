# OrderSeal clean reproduction receipt

## Fast candidate addendum — 2026-08-31

Status: **hackathon package GO at local/historical-provider proof layers; external submission remains unperformed**

- Code/evidence commit: `f1f71a4d3327fd824e7b11ef093c54ea062a7d8d`
- Exact-tree checks: Ruff passed; mypy passed across 15 source files; pytest reported `110 passed, 1 warning in 1.73s`
- Provider/API execution: none; the frozen provider run was not retried
- Offline score: 48/48 completed and retained; DirectBuy 12/24, OrderSeal 19/24, paired mean +29.17 percentage points
- Scoring report SHA-256: `f7c646ff87554b8f40a818f72de3ff5561a91a94fc13703c026c5aed12320a15`
- Scoring seal SHA-256: `6f4944ba0fd36afea5f72af285ce363f2f6efcbaf76c92d3b1c7f9b012c5c10d`
- Fresh sanitized export: 12 generated files matched `submission/evidence/` byte-for-byte; the committed browser screenshot is intentionally separate from the exporter output

The current scorer fails closed on malformed effect cardinality, forces failed rows unsafe while retaining the frozen denominator, and verifies the score seal during export. The provider comparison remains classified as historical post-execution evidence because the included preregistration says `scored_execution_authorized=false` and freezes an earlier scorer.

## Earlier clean archive receipt — preserved historical evidence

Status: **local reproduction passed for commit `53f26c6`; strict external release remained HOLD**

## Candidate and environment

- Source commit: `53f26c65022092715b9dddbdbed1eb89d5600d36`
- Clean directory: `/private/tmp/orderseal-final-repro.xRo35F` (ephemeral)
- Source materialization: `git archive 53f26c6 | tar -x -C <clean-directory>`
- OS: macOS 27.0 (`26A5421a`, arm64)
- Python: CPython 3.13.11
- `uv`: 0.10.12
- Dependency resolution: 23 packages; 22 installed into a new `.venv`
- Provider/API execution: none
- Credential use: none; no `.env` was copied or read

## Immutable evidence mounts

The source archive intentionally excludes git-ignored raw evaluation databases. Before verification, the following existing evidence was copied into the clean directory:

```text
artifacts/scored-20260830-deepseek-v4-flash-0731-baidu-fp8/
artifacts/scored-20260830-deepseek-v4-flash-0731-baidu-fp8-execution-seal.json
artifacts/scored-20260831-openai-gpt-5-6-luna-qualified/
artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-execution-seal.json
```

The qualified Luna mount contained exactly 243 files (11 MiB). Its execution-seal SHA-256 was `670edd663374b076c918ce9584c0c7187f76555f3f0d907b02bffd6abcf34ced`.

## Commands and observed results

```bash
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache uv sync --extra dev
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache uv run --extra dev ruff check .
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache uv run --extra dev mypy app evals tools/export_submission_evidence.py
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache uv run --extra dev python -m pytest -q
```

Observed:

- Ruff: `All checks passed!`
- mypy: `Success: no issues found in 15 source files`
- pytest: `108 passed, 1 warning in 2.23s`
- Warning: upstream Starlette/httpx deprecation only

Offline scoring command:

```bash
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache uv run --extra dev \
  python -m evals.score \
  --run-set artifacts/scored-20260831-openai-gpt-5-6-luna-qualified \
  --execution-seal artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-execution-seal.json \
  --output scoring-report.json
```

Observed:

- 48 assignments, 48 completed, denominator 48
- DirectBuy safe task outcome: 12/24 (50.00%)
- OrderSeal safe task outcome: 19/24 (79.17%)
- Paired mean OrderSeal minus DirectBuy: +29.17 percentage points
- Reproduced report SHA-256: `70b72262c78a24418fab57e63d4aba3547139cfe6bb835ad7da908d5751f4dc5`
- Reproduced score-seal SHA-256: `ed83715d1b259598bfc14054b6c25a249ba86c84794a4a259b7c756fd6ac5ec1`
- Both hashes exactly match `submission/evidence/`

Sanitized export command:

```bash
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache uv run --extra dev \
  python tools/export_submission_evidence.py \
  --run-set artifacts/scored-20260831-openai-gpt-5-6-luna-qualified \
  --execution-seal artifacts/scored-20260831-openai-gpt-5-6-luna-qualified-execution-seal.json \
  --scoring-report scoring-report.json \
  --preregistration preregistration-luna-v1.json \
  --output evidence-reproduced
```

Observed: `file_count: 12`.

Real-browser command, with the clean source served on loopback in evaluation mode:

```bash
ORDERSEAL_EVAL_MODE=1 \
ORDERSEAL_DB_PATH=/private/tmp/orderseal-clean-browser.sqlite3 \
ORDERSEAL_ORIGIN=http://127.0.0.1:8765 \
UV_CACHE_DIR=/private/tmp/orderseal-final-repro-uv-cache \
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765

NPM_CONFIG_CACHE=/private/tmp/orderseal-npm-cache \
CODEX_HOME=/Users/raghav/.codex \
/Users/raghav/.codex/skills/playwright/scripts/playwright_cli.sh \
  run-code --filename tools/browser-smoke.js
```

Observed: the supported brief reached exact review, browser-only confirmation returned `ACK_UNKNOWN`, authoritative status recovery returned the verified receipt, and the browser console reported 0 errors and 0 warnings.

The combined install/static/test/score/export command completed in approximately 7 seconds after local command start; the clean-browser check completed in approximately 17 seconds. These timings are workstation observations, not benchmark claims.

## Proof boundary and HOLDs

This receipt proves deterministic local source verification, sealed offline scoring, sanitized export, and a local real-browser flow for the exact source commit above. It does not prove deployment, installed-product behavior, real commerce, payment safety, staging, production, video hosting, or external submission.

The provider execution is bound to frozen implementation revision `8be0a86817abbb7132b96a77e647e5bcb927dfb3`; the submission candidate contains later local UI and hardening changes and was not provider-rerun. The preregistration records scorer digest `d7285215…`, while the appended reproduction scorer is `526cfcb7…`. The headline effect metrics match the earlier frozen score, but strict exact-scorer preregistration compliance is unresolved. The public bundle also excludes raw databases and capability/session material, so independent rescoring requires controlled access to the evidence mount.

Provider cost is unavailable for all 48 rows; wall-clock provider latency, real human seconds, and reliable clarification-answer counts were not persisted. No significance or generalization claim is authorized.

Historical strict release verdict: **needs-human / HOLD** pending resolution or explicit acceptance of the scorer-identity limitation, creation and hosting of the required under-five-minute video, and user-authorized external upload/submission. The later pragmatic decision is recorded in [`FAST_SUBMISSION_DECISION.md`](FAST_SUBMISSION_DECISION.md).
