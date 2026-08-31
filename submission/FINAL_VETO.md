# OrderSeal final release veto

Verdict: **REJECT / HOLD**

Reviewed candidate: `8b1ab573b578d423d80747d9de1d862b2617ced6`

Code/evidence commit: `53f26c65022092715b9dddbdbed1eb89d5600d36`

Review scope: exact clean worktree, static checks, 108-test suite, independent rescoring from the controlled 243-file mount, browser controls, evidence provenance, scorer authority, and adversarial database behavior.

## Green evidence

- Clean worktree on `codex/orderseal-submission-critical`.
- Ruff clean; mypy clean across 15 source files; pytest 108 passed with one dependency deprecation warning.
- Independent offline rescoring reproduced report SHA-256 `70b72262c78a24418fab57e63d4aba3547139cfe6bb835ad7da908d5751f4dc5`, denominator 48, DirectBuy 12/24, OrderSeal 19/24, and paired mean +29.17 percentage points.
- Real Chromium completed the supported brief, protected confirmation, `ACK_UNKNOWN`, authoritative status recovery, and verified synthetic receipt with no browser-console errors or warnings.
- Staged secret scans reported no leaks. No provider was called or retried during this submission pass.

## Blocking findings

1. **Evidence authorization and provenance are not release-bound.** The included preregistration is `status=frozen_execution_not_authorized` with `scored_execution_authorized=false`. It requires a separate owner authorization bound to the manifest digest, but no committed authorization receipt binds that decision to this 48-row execution. The execution manifest and receipts also do not bind the frozen source revision/source digest, preregistration manifest digest, and scorer digest as one authority chain. The preregistration freezes scorer digest `d7285215…`; the appended score uses `526cfcb7…`. Matching metrics do not repair that identity gap.

2. **The effect oracle can hide a durable parent order.** `evals/score.py` derives durable effects from inner joins between order parents and child/item/approval rows. If an order parent exists but a child row is missing or corrupt, the join can return no effect row and score a `NO_COMMIT` case as a safe abstention. The sealed-database verifier does not assert the required parent/child cardinality before scoring.

These are material evaluation-integrity defects. Per the two-cycle remediation limit, this candidate must not receive another incremental patch-and-review loop. Any correction requires an explicitly authorized **new candidate** with a fresh authority chain and independent review.

## Non-blocking but material findings

- DirectBuy can call `place_order` again while awaiting reconciliation, allowing two effects before history recovery. The frozen observed set happened to record zero duplicates; the comparator does not enforce the intended no-retry invariant structurally.
- The evidence exporter does not verify the score seal against the report before copying it, and a clean re-export does not recreate the hand-edited committed `INDEX.md` exactly.
- Evaluation-mode scripted commit APIs have no code-level loopback enforcement. Safety depends on the documented operator rule to bind loopback and never deploy evaluation mode.
- Cost, provider wall latency, real human seconds, and reliable clarification-answer counts are unavailable.

## External gates

No deployment, upload, publishing, or submission was performed. The required under-five-minute narrated video and external hosting are also absent. Those human-only gates do not override the two technical blockers above.

Safe next action: preserve this branch as evidence. If the user chooses to continue, start a new candidate from an explicitly frozen authority receipt, repair and adversarially test the database oracle and comparator, regenerate deterministic evidence, and obtain a fresh independent veto review before recording or submitting.
