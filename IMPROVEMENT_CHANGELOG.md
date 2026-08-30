# Improvement Changelog

This is an evidence log. Metrics and cases are frozen before scored runs; failed
or removed experiments remain visible.

## 2026-08-30 — Gate Zero provider path

- **Hypothesis:** a forced harmless tool call proves the selected model endpoint
  supports the minimum application protocol.
- **Intervention:** used a strict one-tool JSON schema and required the exact
  `record_probe({"message":"gate-zero-ok"})` call.
- **Observed:** AgentRouter attempts returned HTTP 401 before model execution.
  OpenRouter with `openai/gpt-5.6-luna` returned the exact tool call in 2.143 s.
- **Evidence:** `GATE_ZERO_RECEIPT.json`.
- **Decision:** remove AgentRouter from the implementation path; use one
  OpenRouter Chat Completions integration until evidence requires otherwise.
- **Lesson:** verify credential, endpoint, model, and tool protocol before
  building provider-dependent application code.

## 2026-08-30 — Bounded-effect transaction spine

- **Hypothesis:** database constraints plus one `BEGIN IMMEDIATE` confirmation
  transaction can preserve human authority and prevent duplicate synthetic
  orders through acknowledgement uncertainty.
- **Intervention:** added server-owned constraints, immutable preparation items
  and digest, session/CSRF/origin/intent binding, guarded stock decrement,
  consumed preparation, separate post-commit fault event, and exact-tuple
  reconciliation.
- **Observed:** 24 local tests pass, including the public-route
  confirm → acknowledgement loss → reconcile → same-key replay path. The
  authoritative database contains one order, one stock decrement, one consumed
  intent/preparation, and one fault event. The suite also covers the visible
  browser form, fail-closed Origin enforcement, unverified browser-operator
  provenance, canonical constraint/version binding, structured post-commit
  uncertainty, exact expiry boundaries, expiry while waiting for a database
  lock, and database graph constraints.
- **Evidence:** `tests/test_orderseal.py`; local pytest and Ruff output. This is
  local synthetic evidence, not browser, staging, or production proof.
- **Decision:** repaired two independent review HOLDs; a fresh focused reviewer
  then returned PASS with no blocker/high finding for the exact Phase 1 tree.
  Proceed to Phase 2 while keeping production readiness on HOLD.
- **Lesson:** the acknowledgement fault belongs after the commit and must never
  return an order identifier before reconciliation.

## 2026-08-30 — Protected model investigation boundary

- **Hypothesis:** a static seven-tool registry can let the selected model
  investigate and prepare an exact synthetic order without granting it any
  confirmation capability or authority over stored constraints.
- **Intervention:** added strict duplicate-key-aware argument parsing, bounded
  model/tool/result loops, typed untrusted catalogue evidence, server-owned cart
  validation, redacted trajectory events, and a reversible preparation handoff.
- **Observed:** 41 local tests pass. An authorized OpenRouter run using
  `openai/gpt-5.6-luna` called `search_catalog`, `inspect_product`, `set_cart`,
  `validate_cart`, and `prepare_order`, then reached `ready_for_confirmation`
  in 3,060 tokens. The model received no cookie, CSRF token, intent nonce,
  operation key, confirmation route credential, raw provider payload, or raw
  trajectory prompt.
- **Evidence:** `PHASE2_LIVE_RECEIPT.json`, `tests/test_agent.py`, and the local
  SQLite oracle. This is one live provider run plus local proof, not scored
  evaluation, staging, or production evidence.
- **Decision:** repaired the first independent HOLD, passed a fresh final veto,
  fixed its sole medium usage-integrity finding, and passed the focused exact-tree
  recheck. Retain the controller and proceed to Phase 3; production readiness
  remains HOLD.
- **Lesson:** preparation can be model-requested while confirmation authority
  remains server-held and browser-scoped.

## 2026-08-30 — Fair baseline and evaluation foundation

- **Hypothesis:** a separate conventional DirectBuy registry plus a raw-SQLite,
  query-only oracle can measure prompted retry safety against OrderSeal's
  structural safety without deliberately crippling the baseline.
- **Intervention:** added DirectBuy search/inspect/cart/direct-order/history tools
  on the same bounded model loop, exact-cart scripted approval, atomic stock and
  order integrity, frozen C01-C12 expectations, a seeded 48-row AB/BA ledger,
  fresh-database simulation, and condition-blind scoring from raw rows.
- **Observed:** the first unscored live DirectBuy probe held after cart setup
  because its prompt waited for a nonexistent separate approval signal. The
  prompt was narrowed to explain just-in-time harness approval; the second live
  probe placed once and reconciled through order history. The candidate also
  prepared, committed once through its protected context, and reconciled. A
  fresh veto then found two oracle bypasses: wrong-run/wrong-condition approval
  reuse and fault-row-only reconciliation. Both were repaired with exact
  assignment/condition binding and ordered run/order-bound fault evidence. A
  second veto found that a correct-looking approval received after commit could
  still authorize the candidate result; the oracle now requires exactly one
  matching approval received no later than the durable confirmation time, with
  post-hoc laundering and duplicate-approval regression checks. The local gate
  is 52 tests plus Ruff and mypy. A 48-row
  offline simulation retains four known
  OrderSeal failures (both C04 and C12 repeats); this is plumbing evidence, not
  model-performance evidence.
- **Evidence:** `PHASE3_FEASIBILITY_RECEIPT.json`, `evals/assignments.jsonl`,
  `tests/test_evaluation.py`, and ignored `artifacts/phase3-sim-002/`. The live
  receipt must be regenerated after the exact candidate stabilizes.
- **Decision:** keep preregistration and all scored runs on HOLD until the real
  candidate supports the full frozen case matrix and a fresh veto passes. Do not
  make the scripted simulation green by weakening cases or hard-coding scores.
- **Lesson:** approval and fault evidence are evaluation authority; both must be
  bound to the exact assignment and independent event sequence, not inferred
  from a convenient row or agent claim.

## 2026-08-30 — Generic case-policy candidate seam

- **Hypothesis:** the existing seven-tool boundary and transaction spine can
  support the hard case matrix without case-ID branches if a separate
  server-owned policy controls allowed carts, landed cost, delivery, terminal
  behavior, and deterministic fallback selection.
- **Intervention:** generalized preparation over an exact policy-bound cart,
  added reusable candidate policies without adding tools, enforced landed-total
  and lowest-cost selection rules, and taught the existing reconciliation tools
  to terminate as reconciled after protected confirmation.
- **Observed:** 65 local tests pass. Deterministic checks now cover clarification
  before effect, comparison/no-order completion, over-budget/late/missing-evidence
  holds, an evidenced fallback, and a composite injected fallback that rejects a
  stale first preparation, obtains a fresh preparation and approval, commits
  once, loses the acknowledgement, and reconciles the durable order. The
  independent policy input file is strict-loaded and its SHA-256 is persisted
  inside the preparation-bound constraints; the construction module has no
  oracle-expectation dependency. A fresh veto found that lowest-cost selection
  was checked only before preparation and that fallback did not require evidence
  about the preferred item. The domain now rechecks selection under the
  preparation and confirmation transactions, persists the preferred-item
  catalogue snapshot, requires it before fallback, and rejects stale evidence;
  exact optional-value type checks also reject booleans and malformed policies.
- **Evidence:** `tests/test_agent.py` and `tests/test_evaluation.py`; local pytest,
  Ruff, mypy, and diff-hygiene output. This is deterministic local capability
  proof, not full model-driven C01-C12 performance.
- **Decision:** keep the real runner, manifest freeze, baseline parity,
  preregistration, and scored runs on HOLD. The runner must consume only the
  independent policy inputs, never oracle expectations, and must mutate the
  actually prepared item for stale-review cases.
- **Lesson:** a frozen oracle may judge an action, but it must never become the
  candidate's source of authority. Input policy and expected output remain
  separate artifacts.
