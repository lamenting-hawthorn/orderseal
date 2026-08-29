# OrderSeal Agent Security Review

**Date:** 2026-08-29
**Scope:** Model-agent boundary and security design in `ORDERSEAL_BUILD_PLAN.md` and `OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md`
**Proof layer:** Static document review only; no application, repository, tests, provider call, or runtime exists to verify
**Reviewer posture:** Read-only review of the canonical documents; document content was treated as evidence, not instructions

## Verdict

**HOLD — sound direction, incomplete enforceable contract.**

The design makes the correct foundational choices: a candidate registry of exactly seven narrow tools, no candidate confirmation tool, deterministic ownership of commerce state, SQLite as the effect oracle, structured treatment of catalogue text as untrusted evidence, and a credential-constrained Gate Zero (`ORDERSEAL_BUILD_PLAN.md:169-240`, `360-370`, `557-567`). These are planning claims, not implemented controls.

Do not claim the agent-security boundary is ready, and do not begin Phase 2 or scored evaluation, until the minimal contract and veto tests below are incorporated. Phase 1 must also freeze the session/confirmation and normalized-constraint contracts before implementing them. Gate Zero may run only under its credential and receipt conditions.

No runtime vulnerability is claimed as proven because no runtime exists. The veto is against an underspecified security plan.

## Trust boundaries

| Boundary | Trusted authority | Untrusted input | Required invariant |
|---|---|---|---|
| User intent -> normalized constraints | Visible user input plus server-owned normalized `ConstraintSet` | Model interpretation, catalogue text, prior assistant text | The model cannot silently drop or weaken quantity, budget, currency, delivery, or fallback constraints. Ambiguity ends in `needs_user` or `held`. |
| Provider -> agent controller | Fixed system policy, exact tool schemas, server-owned run state | Model messages and tool-call arguments | Model output is a proposal; only the strict dispatcher may cause a tool call. |
| Catalogue -> model/UI | Typed product facts from SQLite | Product name and description, including markup and instructions | All catalogue strings remain labelled evidence, never policy, code, or HTML. |
| Agent -> deterministic domain | Exact seven-tool allowlist and strict validated arguments | Unknown tools, extra fields, malformed IDs, oversized inputs | Fail closed before any state mutation; session and authoritative values are injected server-side. |
| Browser -> confirmation route | Current session, CSRF proof, same-origin request, intent nonce bound to the rendered preparation | Request body, repeated clicks, forged/cross-session identifiers | Only a fresh, visible confirmation intent can reach commit; the model receives none of the capability material. |
| Confirmation route -> SQLite | Transactional domain service and current catalogue state | Stale preparation, replay, new operation key, concurrent request | One preparation creates at most one order; uncertain acknowledgement permits reconciliation only. |
| Runtime -> trajectory/receipt artifacts | Allowlisted event serializer and authoritative oracle | Prompts, model text, tool data, errors, identifiers | Redact before persistence, escape on display, omit secrets and hidden reasoning, and preserve enough typed evidence to reproduce claims. |
| Local environment -> model provider | User-authorized API path and environment-injected credential | Process environment, SDK errors/debug logs, provider responses | Credentials are never read back, echoed, logged, committed, or written to artifacts. |
| Evaluation harness -> baseline/candidate | Frozen cases, limits, fault assignment, and SQLite oracle | Agent claims and simulated approval events | Simulated approval is labelled as simulation; it cannot be fabricated by either model. Candidate and baseline registries remain isolated. |

The official review requires simulated consequential actions to retain human approval and credentials to remain outside the submission (`OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md:57-68`). The build plan correctly limits its claims to static, local, synthetic, and hosted proof layers (`ORDERSEAL_BUILD_PLAN.md:708-715`).

## Tool contract findings

### 1. Seven-tool candidate registry: correct inventory, missing enforcement

The plan lists exactly:

1. `search_catalog`
2. `inspect_product`
3. `set_cart`
4. `validate_cart`
5. `prepare_order`
6. `get_order_status`
7. `get_receipt`

It excludes `confirm_order`, raw SQL, arbitrary HTTP, filesystem, shell, and browser-control capabilities (`ORDERSEAL_BUILD_PLAN.md:226-240`). The Phase 2 gate checks only that no confirmation tool is registered (`ORDERSEAL_BUILD_PLAN.md:602-613`), which does not prove that aliases, dynamic registration, provider passthrough, a generic request tool, or a callable internal commit function are unreachable.

**Required:** one immutable candidate dispatcher maps only these seven public names to seven handlers. Reject unknown names and duplicate/extra arguments. No dynamic registration, alias, provider-native tool passthrough, or generic invocation mechanism. The model runtime receives no route credential, cookie, CSRF token, confirmation-intent nonce, operation key, database handle, arbitrary URL, path, shell, or code-execution capability.

The DirectBuy `place_order` tool is a separate evaluation-only registry and must never be imported into or selectable by the candidate dispatcher (`ORDERSEAL_BUILD_PLAN.md:376-390`).

### 2. Confirmation authority: good separation, incomplete proof

The current contract requires a session cookie, CSRF token, preparation ID and digest, and a retained idempotency key; it says only the UI enters `CONFIRMING` (`ORDERSEAL_BUILD_PLAN.md:199-209`, `242-263`). “Browser-only” and “human-only” are not enforceable properties by route naming alone.

**Required:** the commit route is `POST` only and requires:

- an opaque, high-entropy, expiring server-side session;
- an `HttpOnly`, `SameSite=Lax` cookie and `Secure` whenever HTTPS is used;
- a synchronizer CSRF token stored hashed and compared in constant time;
- an exact allowed `Origin` check when the header is present and a fixed host configuration;
- a short-lived, single-use confirmation-intent nonce minted for the rendered confirmation card and bound to session ID, preparation ID, preparation digest, and current cart/constraint digest;
- an idempotency key that stabilizes retries but grants no authority by itself;
- server-side revalidation and commit through one transaction.

The agent must not receive any of this capability material. Same-key replay returns the original order; a new key against a consumed preparation rejects. A browser session proves possession of the confirmation capability, not a universal human identity; the visible E2E path is the evidence for the human-confirmation claim.

### 3. Instruction versus evidence: correct hierarchy, missing typed enforcement

The plan distinguishes user instructions, deterministic facts, untrusted product data, prior model text, and authoritative SQLite state (`ORDERSEAL_BUILD_PLAN.md:360-370`). However, only the description has a named `untrusted_description` field, while product names are also declared untrusted. The prompt-construction rule and provenance shape are unspecified.

**Required precedence:**

```text
fixed security policy
  > visible user-approved ConstraintSet
  > typed deterministic tool facts and validation
  > catalogue strings marked untrusted evidence
  > previous model prose
```

Product name and description must be returned in an evidence envelope such as `{value, source: "catalogue", catalogue_version, untrusted: true}` and inserted only as tool data, never concatenated into system/developer instructions. Unknown provenance fails closed.

### 4. Constraint authority is undefined

The deterministic domain is supposed to validate explicit user constraints and bind a `constraint_digest`, but the plan does not define how a chat-like brief becomes authoritative structured constraints (`ORDERSEAL_BUILD_PLAN.md:11-18`, `86-99`, `169-182`, `303-317`). If the model alone supplies or edits that structure, injected catalogue text can cause it to omit the budget, quantity, delivery deadline, or fallback restriction while deterministic validation still “passes.”

**Required:** before preparation, store a server-owned `ConstraintSet` with quantity, budget/currency, delivery deadline, permitted substitutions, and unresolved fields. It must be derived by deterministic parsing where possible and visibly accepted or corrected by the user for any material ambiguity. `validate_cart` and `prepare_order` read this server-owned object; tool arguments cannot replace it. Its digest is displayed on the confirmation card and bound to the preparation.

### 5. Tool argument and result validation is not concrete

Pydantic validation and malformed-argument testing are planned (`ORDERSEAL_BUILD_PLAN.md:143-153`, `602-624`), but field constraints and ownership rules are absent.

**Required defaults:** strict types, `extra="forbid"`, normalized Unicode, control-character rejection outside ordinary whitespace, and these initial caps:

| Tool | Model-controlled arguments | Server-controlled context/result cap |
|---|---|---|
| `search_catalog` | query 1-200 characters; `limit` 1-20 | Session/run injected; at most 20 typed summaries, 16 KiB total |
| `inspect_product` | SKU 1-64 characters using a fixed SKU grammar | Exact SQLite row; name <= 200 and description <= 2,000 characters; 8 KiB total |
| `set_cart` | 0-25 distinct items; SKU grammar above; integer quantity 1-100 | Replace current session cart only; prices, stock, versions, totals, and session ID ignored if supplied and rejected as extra fields |
| `validate_cart` | no authoritative values | Reads current session cart and server-owned `ConstraintSet`; 16 KiB typed report |
| `prepare_order` | no price, total, session, digest, expiry, or operation-key fields | Creates from validated server state; fixed short TTL; one pending preparation per cart version |
| `get_order_status` | opaque preparation reference only | Session scoped; bounded enum/state response; no cross-session existence oracle |
| `get_receipt` | opaque order/preparation reference only | Session scoped; max 25 item snapshots and 16 KiB total |

Validation failures return typed, non-secret errors. Do not silently coerce types or truncate invariant-bearing data. An oversized result returns `limit_exceeded` and moves the run to `held` or `needs_user`; search may return an explicit bounded subset with `has_more=true`.

### 6. Step, time, and retry limits are named but not frozen

The plan requires equal limits and denominator-bearing timeouts but gives no values or failure semantics (`ORDERSEAL_BUILD_PLAN.md:184-197`, `392-403`, `501-518`, `602-624`).

**Initial frozen limits:** maximum 16 model responses, 24 total tool calls, 120 seconds wall-clock per run, 30 seconds per provider response, 3 seconds per local tool call, 8 KiB serialized arguments per call, and the result caps above. No automatic retry of `set_cart`, `prepare_order`, baseline `place_order`, confirmation, or any request with an ambiguous outcome. A limit, cancellation, or malformed repeated call terminates as `held` or `needs_user`; after `ACK_UNKNOWN`, only `get_order_status` and `get_receipt` remain callable.

These constants may be tuned before prompts/cases are frozen, but the final values must be versioned, identical across conditions where capabilities match, recorded in receipts, and unchanged after scored results are observed.

### 7. Trajectory sanitization needs an allowlist, not a promise

The plan specifies sanitized JSONL events and prohibits secrets, headers, cookies, CSRF tokens, environment values, and hidden chain-of-thought (`ORDERSEAL_BUILD_PLAN.md:466-499`, `602-612`). It does not define redaction timing, identifier treatment, control-character handling, or viewer safety.

**Required:** construct persisted events from an allowlist after validation; never serialize raw request/response objects or process environments. Pseudonymize session, preparation, operation, and order identifiers in public artifacts. Cap every field and event, normalize line/control characters, omit hidden reasoning, and record only assistant-visible summaries. Escape all trajectory/catalogue text when rendered; apply a restrictive local CSP if an HTML viewer exists. Run secret-pattern and forbidden-field scans before artifacts are accepted, while acknowledging that pattern scanning cannot prove absence of every secret.

### 8. Gate Zero is directionally correct but its pass receipt is incomplete

Gate Zero correctly requires a real authorized tool-calling round trip, environment-only credential handling, canonical model identity, and a stop after one unresolved hour; it explicitly proves access only (`ORDERSEAL_BUILD_PLAN.md:155-165`, `557-567`). The independent review also marks model access unverified (`OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md:180-190`, `207-214`).

**Required Gate Zero receipt:** provider, canonical model ID, SDK/library version, timestamp, prompt digest, tool-schema digest, observed validated call to one harmless local probe tool, observed final response, success/failure, latency, token usage, and cost if exposed. Store no prompt/response headers, credential, environment dump, or raw provider error. Disable SDK HTTP/debug logging, sanitize exceptions before display/persistence, and prove that deterministic tests and app startup have a no-key path. A mock, interactive subscription, or unverified alias does not pass.

## Minimal agent contract

1. **Authority:** The model may investigate, propose a cart, request deterministic validation/preparation, explain evidence, and reconcile. It may never confirm, commit, manufacture approval, weaken a user-approved constraint, or choose an authoritative price/stock/version/total.
2. **Capabilities:** Candidate dispatch is a static exact allowlist of the seven named tools. There are no aliases, dynamic tools, generic calls, arbitrary I/O, or provider passthrough. Baseline capabilities live in a distinct evaluation registry.
3. **Context:** The server injects session, run, workflow state, `ConstraintSet`, and catalogue snapshot. The model receives no credentials or capability-bearing browser/confirmation material and cannot supply ownership fields.
4. **Data precedence:** Fixed policy and user-approved constraints outrank deterministic facts; deterministic facts outrank untrusted catalogue evidence; all outrank prior model prose. Untrusted strings remain typed data at prompt and display boundaries.
5. **Validation:** Every HTTP body and tool call uses strict bounded schemas with unknown fields rejected. Server-derived values are never accepted from model arguments. All object access is scoped by the server-injected session and returns indistinguishable not-found/forbidden responses.
6. **Workflow:** Legal terminal states are `ready_for_confirmation`, `needs_user`, `held`, and `complete`. Only deterministic validation enters `VALIDATED`; only the protected UI route enters `CONFIRMING`. `ACK_UNKNOWN` narrows capabilities to reconciliation and never authorizes a new preparation or order.
7. **Confirmation:** A visible confirmation card displays exact normalized constraints, items, versions, quantities, shipping, tax, total, expiry, and digest. A short-lived intent nonce binds that view to the session and preparation. The route revalidates and commits once transactionally.
8. **Budgets:** The numeric step, tool, time, argument, and result limits above are enforced server-side and receipt-bound. Limit exhaustion fails closed without a consequential retry.
9. **Artifacts:** Trajectories are allowlisted, bounded, redacted before write, free of hidden reasoning and capability material, and escaped on display. SQLite—not model prose—determines evaluation truth.
10. **Credentials:** Provider credentials enter only through local environment configuration, remain inaccessible to the model and artifacts, and are never requested, read back, or echoed. Gate Zero is a real, harmless, receipt-bound access check only.

## Threat/control table

| Threat | Existing plan evidence | Required control | Veto condition |
|---|---|---|---|
| Agent confirms or commits | No candidate confirmation tool; separate route (`199-240`) | Static dispatcher, capability isolation, protected POST route, intent nonce | Any candidate tool, alias, generic call, internal handler, or model-held capability can reach commit |
| Baseline authority leaks into candidate | Separate condition descriptions (`376-390`) | Separate registries and explicit condition construction | Candidate can select/import `place_order`, or baseline can fabricate the simulated approval event |
| Prompt injection changes policy or action | Untrusted field, explicit policy, hard case (`360-370`, `420-433`, `503-513`) | Typed provenance, no prompt concatenation, deterministic constraints, escaped UI | Catalogue/model text changes policy, drops a constraint, triggers confirmation/order, or executes markup |
| Model weakens user intent | Constraint digest and validation are named (`303-317`, `343-352`) | User-visible server-owned `ConstraintSet` | Model alone can add, remove, or alter a material constraint used for preparation |
| CSRF/session theft or cross-session access | Cookie + CSRF; session-scoped queries (`199-209`, `269-274`, `501-510`) | Entropy, expiry, cookie flags, synchronizer token, constant-time compare, Origin check, intent binding | Missing/wrong CSRF, origin, session, digest, or intent succeeds; any cross-session read/mutation leaks existence or data |
| Malformed calls or resource exhaustion | Pydantic and named limits (`143-153`, `516`, `602-624`) | Strict schemas, caps, timeouts, typed errors, fail-closed terminal states | Unknown/oversized/malformed input is accepted, a loop is unbounded, or truncation hides safety data |
| Replay, duplicate, or stale commit | Unique keys and transactional revalidation (`318-358`) | `BEGIN IMMEDIATE`, uniqueness, consumed state, current-state recomputation | Durable count differs from one after retry/ACK loss, a new key consumes an old preparation, or stale data commits |
| Hallucinated success | SQLite oracle and reconciliation (`211-224`, `434-464`) | Oracle-only scoring and post-uncertainty capability narrowing | A success metric or receipt outcome is derived from model prose |
| Artifact/trajectory leak or stored XSS | Sanitized events and forbidden fields (`466-499`) | Allowlist serializer, pseudonyms, caps, redaction-before-write, escaped viewer/CSP | Credential, bearer/header, cookie, CSRF, environment value, raw hidden reasoning, capability ID, or executable markup appears |
| Credential/provider misuse | Gate Zero credential rules (`155-165`, `557-567`) | Authorized API, debug-log suppression, sanitized errors, non-secret receipt, no-key path | Mock/interactive path counted as real, provider/account authority is unclear, secret is exposed, or Gate Zero remains unresolved |
| Fault injector escapes evaluation | Exact eval-mode flag (`517`) | Startup refusal unless exact flag and evaluation command/context agree | Fault injection can activate silently or outside an explicitly labelled evaluation run |

## Required tests

These are minimum veto tests, not a full suite:

1. **Registry snapshot:** candidate names equal the exact seven-name set; reject aliases, unknown tools, `confirm_order`, `place_order`, raw/provider passthrough, and dynamic registration.
2. **Commit reachability:** from every candidate handler and agent state, prove no call path reaches the confirmation route or commit service. Direct internal invocation without protected request context rejects.
3. **Strict schema matrix:** reject extra fields, wrong types, coercions, malformed IDs/SKUs/digests, duplicate cart items, zero/negative/excessive quantities, oversized arguments/results, and URL/path/session/price/stock fields.
4. **Constraint integrity:** injected model/catalogue text cannot remove or weaken quantity, budget/currency, delivery, or substitution rules; mismatched `ConstraintSet` digest rejects; ambiguity requires user action.
5. **Prompt injection and XSS:** malicious name and description values containing instruction overrides, repeat-order demands, HTML/script, Unicode edge cases, and control characters cannot alter policy/state and render only as escaped text.
6. **Confirmation boundary:** reject GET, missing/wrong CSRF, cross-origin request, expired/reused intent nonce, wrong session/preparation/digest, and forged idempotency key; accept only the valid bound POST.
7. **Session isolation:** every cart, preparation, status, order, receipt, and error path is adversarially exercised from a second session without leaking existence or data.
8. **TOCTOU and exactly once:** change price, stock, version, and delivery before confirmation; stale state holds. Same-key double click/refresh/ACK loss returns one original order; a new key on the consumed preparation rejects; durable count remains one under concurrent requests.
9. **Loop limits:** hit every model/tool/time/argument/result cap and provider cancellation. Each run records a denominator-bearing failure, ends `held`/`needs_user`, and performs no new consequential retry. After `ACK_UNKNOWN`, all tools except status/receipt reject.
10. **Trajectory sanitizer:** seed synthetic API keys, bearer/header/cookie/CSRF/environment strings, capability IDs, multiline/control characters, markup, provider errors, and hidden-reasoning-like fields. Forbidden material never persists; public rendering remains inert; required event schema/digests remain reproducible.
11. **Gate Zero:** no-key deterministic startup/tests pass; one authorized harmless real tool call through the intended application API produces only the allowed receipt; provider errors and enabled debug modes do not leak the credential.
12. **Evaluation authority:** candidate and baseline registries are isolated; only the harness can create a labelled simulated approval; neither model can fabricate it; limits/faults are frozen and SQLite alone scores outcomes.
13. **Fault-mode refusal:** fault injection is impossible unless `ORDERSEAL_EVAL_MODE=1` and the explicit evaluation runner is active; startup/configuration otherwise fails closed.
14. **Parameterized and bounded storage:** adversarial strings never alter SQL structure; schema constraints and foreign keys reject invalid state; artifact/event size stays bounded.

Phase 2 does not pass on a registry-absence assertion alone. It passes only when tests 1-5 and 9 succeed with a real model investigation. Scored evaluation does not start until all fourteen deterministic/integration tests pass.

## Residual risks

- No implementation or runtime evidence exists. Session isolation, CSRF behavior, dispatcher reachability, transaction semantics, sanitization, provider behavior, and every test above remain unproven (`ORDERSEAL_BUILD_PLAN.md:3-7`).
- Prompt instructions cannot guarantee model obedience. Deterministic authority separation limits impact, but reversible nuisance calls, denial of service, misleading explanations, and unnecessary holds remain possible.
- User registration, tenancy, and production identity are explicit non-goals (`ORDERSEAL_BUILD_PLAN.md:71-82`). A valid local session is the practical approval principal; session compromise is not solved by this demo.
- A confirmation intent proves possession of a browser/session capability, not that a particular natural person understood the card. Visible E2E evidence and honest wording are required.
- The DirectBuy baseline intentionally has broader synthetic authority. Registry/configuration isolation is therefore a high-value test boundary.
- Redaction patterns can miss novel secrets, and provider, proxy, operating-system, or crash logs may exist outside application artifacts. Gate Zero must limit claims to the inspected application path.
- SQLite and a local single service do not prove production concurrency, distributed idempotency, real-payment safety, or general browser security. The acknowledgement-loss case is a deterministic simulation, not a real outage (`ORDERSEAL_BUILD_PLAN.md:343-358`, `708-715`).
- The proposed numeric caps are safe starting defaults, not measured optimal values. Tune only before frozen evaluation and report the final values.
- Any public trajectory containing user-entered data remains a privacy risk outside the current synthetic-only scope.

## Recommended plan amendments

1. Insert the **Minimal agent contract** above before Phase 2 and make it an immutable build/evaluation contract.
2. Add a server-owned, user-visible normalized `ConstraintSet`; bind its digest to preparation and confirmation. Make silent model weakening a veto.
3. Replace “only the browser UI may call” with the exact POST/session/cookie/CSRF/Origin/intent-nonce contract and clarify that the idempotency key is not authorization.
4. Strengthen the Phase 2 gate from “seven tools and no confirmation name” to exact dispatcher equality, commit-unreachability, strict schema, injection/XSS, constraint-integrity, and budget tests.
5. Specify strict schemas and the initial numeric limits in one constants table shared by runtime, evaluator, receipts, and tests; no parallel policy copies.
6. Define catalogue evidence envelopes for both name and description, forbid prompt concatenation into privileged messages, and reject unknown provenance.
7. Define a single allowlist trajectory serializer that redacts before write, pseudonymizes capability-bearing IDs, omits hidden reasoning, caps fields/events, and supports only escaped rendering.
8. Define the Gate Zero receipt, SDK/debug-log policy, sanitized provider-error path, secret scan, and no-key startup/test proof. Keep its claim limited to authorized access.
9. Isolate the DirectBuy registry and require a harness-issued, receipt-recorded simulated approval that neither model can create. Label it simulated, not human.
10. Add all fourteen veto tests to the Phase 1-3 gates. Freeze their assertions before scored runs and do not weaken them after results.
11. Preserve the existing strengths: transactional revalidation/idempotency, SQLite-only oracle, equal evaluation limits, denominator-bearing failures, no arbitrary I/O, synthetic-only scope, and explicit evidence-layer limits.

### Veto conditions

Stop the affected phase and report `HOLD` if any of the following is true:

- Gate Zero uses an unauthorized or non-programmatic path, exposes a credential, lacks the non-secret receipt, or remains unresolved after one hour.
- The candidate registry differs from the exact seven tools, includes generic/dynamic/provider passthrough, or any agent path can reach commit.
- The model can supply session ownership, authoritative commerce values, confirmation capability material, or a weaker constraint set.
- Missing/wrong session, CSRF, origin, confirmation intent, preparation digest, or cross-session requests do not fail closed.
- Product or model text changes policy, constraints, confirmation, durable state, or rendered code/markup.
- Any malformed or oversized call bypasses validation; any loop, result, retry, or timeout path is unbounded or can duplicate an order.
- Same-key retry fails to return the original order, a new key consumes an old preparation, stale state commits, or durable order count is not exactly one.
- A trajectory/artifact contains credentials, headers, cookies, CSRF/environment values, hidden reasoning, capability-bearing identifiers, or executable unescaped content.
- The evaluation harness lets a model fabricate approval, mixes baseline and candidate capabilities, changes frozen gates after results, or scores success from model prose.
- A required security invariant lacks evidence at the proof layer being claimed. The plan already requires holding such a capability (`ORDERSEAL_BUILD_PLAN.md:717-727`).

Until these amendments and tests exist, the defensible claim is: **OrderSeal has a promising static security design for a synthetic local demo; its agent authority boundary is not yet implemented or proven.**
