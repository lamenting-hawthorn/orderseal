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
