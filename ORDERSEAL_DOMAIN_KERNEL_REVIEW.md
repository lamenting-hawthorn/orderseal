# OrderSeal Deterministic Domain Kernel Review

**Review scope:** SQLite schema, preparation binding, session isolation, confirmation transaction, replay semantics, stale quotes, simulated post-commit acknowledgement loss, receipt truth, and the hour-eight gate.
**Evidence layer:** Static document review only; no application exists and no behavior has been executed.
**Reviewed artifacts:** `ORDERSEAL_BUILD_PLAN.md` SHA-256 `843cef4b9927442aaa8e11009a1909e424950faef82b3acddc830460dc3ef920`; `OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md` SHA-256 `c728ada2ad6bf30481874d42a522f0b1168b94a7af1d0281213217349dece58d`.

## Verdict

**REVISE BEFORE IMPLEMENTATION.** The proposed single-service, single-SQLite-file design is the right small architecture, and `BEGIN IMMEDIATE` plus database uniqueness can enforce an at-most-once durable order effect. The current plan is not yet an executable transaction contract, however. It does not define the preparation digest, persist an immutable quoted-item snapshot, enforce relational session ownership, specify operation-key collision behavior, consume stock, or durably distinguish a post-commit injected fault from a normal response.

The hour-eight gate should remain a hard stop. Passing it may support this narrow claim:

> For one valid, human-confirmed preparation in the tested single-SQLite deployment, retries and a deterministic post-commit acknowledgement-loss simulation produce exactly one durable order, and reconciliation returns that order from authoritative state.

It must not be generalized to distributed exactly-once delivery, real payments, production security, or all failure modes. Before confirmation, the guarantee is zero-or-one; “exactly one” applies only to the accepted-confirmation scenario proved by the integration test.

## Invariant table

| Invariant | Existing plan evidence | Verdict | Minimum enforceable contract |
|---|---|---|---|
| The model cannot commit | Confirmation is a session/CSRF-protected UI route and is absent from the tool registry (`ORDERSEAL_BUILD_PLAN.md:199-209,228-240`). | Directionally sound; “only the browser UI may call” is not literally enforceable. | Only the server confirmation route may invoke the commit function. Require a server-derived session, valid CSRF token, preparation ID/digest, and bounded operation key. Expose no raw HTTP, SQL, or confirmation tool to the agent. Record route-based confirmation provenance durably. |
| One preparation creates at most one order | `orders.preparation_id` is unique and consumption occurs in the same transaction (`ORDERSEAL_BUILD_PLAN.md:318-341,345-355`). | Sound if made DDL, not prose. | `UNIQUE(orders.preparation_id)` plus order insert, item snapshots, stock effect, and preparation consumption in one transaction. A consumed preparation without its matching order is `HELD` as an invariant breach. |
| One operation key cannot identify two effects | `orders.operation_key` is unique (`ORDERSEAL_BUILD_PLAN.md:318-341`). | Collision semantics are missing. | Exact same session + preparation + operation key + preparation digest returns the original order. Any reuse with a different tuple returns a generic conflict and never discloses the existing order. Never replace the key after an unknown outcome. |
| Session ownership fails closed | Every cart, preparation, order, and receipt query must be session-scoped (`ORDERSEAL_BUILD_PLAN.md:95,199-207,503-510`). | Query guidance exists; relational integrity does not. | Derive session only from the cookie. Use composite ownership foreign keys or mandatory owner joins. Never accept a session ID from the request body. Cross-session missing/conflict responses reveal no order ID or existence. |
| Confirmation binds the exact visible quote | The UI sends a preparation digest, and confirmation recomputes it (`ORDERSEAL_BUILD_PLAN.md:36-40,201-207,343-356`). | **Blocking specification gap:** the schema has only `cart_digest` and `constraint_digest`; no preparation digest or immutable quote-item rows (`ORDERSEAL_BUILD_PLAN.md:303-317`). | Define `preparation-digest-v1` over canonical bytes containing the exact item and constraint snapshot, all quoted amounts, and pricing-policy version. Store that digest and its inputs. The confirmation card must render those stored inputs. |
| A stale quote cannot commit | Product versions, stock, prices, and delivery values are reread under `BEGIN IMMEDIATE` (`ORDERSEAL_BUILD_PLAN.md:343-355,503-510`). | Incomplete. `active`, cart version, shipping/tax policy, and stock mutation are unspecified. | Recheck cart version, every quoted product field including `active`, all constraints, totals, and pricing-policy version inside the write transaction. Every mutable catalogue change increments product version. Reject and invalidate stale preparation; require a new visible confirmation. |
| Inventory cannot be oversold | The domain owns stock validation and products store stock (`ORDERSEAL_BUILD_PLAN.md:169-180,275-286`). | **Contradiction:** confirmation checks stock but never decrements or reserves it. | Atomically decrement stock in the order transaction with a guarded update and require one affected row per item. Otherwise explicitly declare stock non-consumable; that weaker option would conflict with current commerce semantics. |
| Concurrent confirmations serialize safely | The plan specifies `BEGIN IMMEDIATE` (`ORDERSEAL_BUILD_PLAN.md:343-356`). | Correct for one SQLite database file; lock handling is unspecified. | Use one connection per request, `PRAGMA foreign_keys=ON`, an explicit busy timeout, and no model/network work while the lock is held. On lock timeout or integrity conflict, do not mint a new key; reconcile the exact tuple or return an unknown/conflict result. |
| Acknowledgement loss occurs after commit | Fault injection is step 10, after commit, and returns no order ID (`ORDERSEAL_BUILD_PLAN.md:345-358`). | Ordering is correct; durable fault evidence is missing. | Exit the transaction successfully before invoking the fault injector. In evaluation mode, persist an order-linked `post_commit_ack_loss` event only after the order is visible, then return a structured unknown response with no order ID. Refuse fault configuration outside evaluation mode. |
| `ACK_UNKNOWN` cannot cause a second order | The state machine forbids a new order and requires reconciliation (`ORDERSEAL_BUILD_PLAN.md:257-263`). | Wording is ambiguous about a same-key retry. | Reconcile first by the exact session/preparation/operation tuple. A transport retry with the same key is safe and returns the same order; a new key is forbidden. No-match remains unknown/held until policy explicitly permits the same-key attempt again. |
| Receipt reflects durable truth | Order items are snapshots and the evaluator reads SQLite rather than agent prose (`ORDERSEAL_BUILD_PLAN.md:211-224,328-330,434-464`). | Sound if receipt construction is constrained. | Build receipts only from `orders`, immutable `order_items`, confirmation provenance, and durable fault events. Never reconstruct from current products, cart state, request data, model text, or trajectory claims. |
| Re-preparing cannot duplicate one intent | The plan allows preparations but defines no active-preparation cardinality. | Missing edge contract. | Permit at most one pending preparation per cart with a partial unique index, or invalidate the previous pending preparation when creating a new one. A stale replacement requires a new human confirmation. |

## Minimal schema/transaction contract

### Schema spine

Use SQLite DDL as the authority. Every identifier, amount, quantity, version, timestamp, status, and digest is `NOT NULL` unless the domain explicitly models unknown. Add `CHECK` constraints for positive quantities, non-negative paise/stock/version values, allowed statuses, digest/key shape, and internally consistent timestamps. Use parameterized SQL only and enable foreign keys on every connection.

The smallest schema that preserves the required truth is:

- `sessions(id PRIMARY KEY, csrf_token_hash, created_at_epoch)`.
- `products(id PRIMARY KEY, sku UNIQUE, ..., unit_price_paise, stock_quantity, delivery_days, version, active)` with checks; every mutable quote field change increments `version`.
- `carts(id PRIMARY KEY, session_id REFERENCES sessions, version, status, updated_at_epoch, UNIQUE(id, session_id))`.
- `cart_items(cart_id REFERENCES carts, product_id REFERENCES products, quantity, PRIMARY KEY(cart_id, product_id))`.
- `preparations(id PRIMARY KEY, session_id, cart_id, cart_version, constraints_json, constraint_digest, preparation_digest, pricing_policy_version, quoted_subtotal_paise, quoted_shipping_paise, quoted_tax_paise, quoted_total_paise, expires_at_epoch, status, created_at_epoch, UNIQUE(id, session_id), FOREIGN KEY(cart_id, session_id) REFERENCES carts(id, session_id))`.
- `preparation_items(preparation_id REFERENCES preparations, line_no, product_id, sku, product_version, quantity, unit_price_paise, delivery_days, PRIMARY KEY(preparation_id, line_no), UNIQUE(preparation_id, product_id))` as the immutable quote the human sees.
- `orders(id PRIMARY KEY, preparation_id UNIQUE, session_id, operation_key UNIQUE, total_paise, status, confirmation_method CHECK(confirmation_method = 'ui_route'), confirmed_at_epoch, UNIQUE(id, session_id), FOREIGN KEY(preparation_id, session_id) REFERENCES preparations(id, session_id))`.
- `order_items(order_id REFERENCES orders, line_no, product_id, sku, product_version, quantity, unit_price_paise, delivery_days, PRIMARY KEY(order_id, line_no))` as immutable receipt data.
- `order_attempts(id PRIMARY KEY, session_id REFERENCES sessions, preparation_id REFERENCES preparations, operation_key, outcome, reason_code, created_at_epoch)` for committed, replayed, and owned rejection attempts. Cross-session probes need not be persisted with foreign object identifiers.
- `fault_events(id PRIMARY KEY, order_id UNIQUE REFERENCES orders, kind CHECK(kind = 'post_commit_ack_loss'), created_at_epoch)` for the deterministic evaluation fault.

Use a partial unique index such as one pending preparation per cart. Do not add an ORM, event bus, reservation service, idempotency service, or generic repository layer.

### Preparation digest v1

Define one canonical payload with an explicit domain/version tag. It contains:

- session-bound preparation and cart identifiers plus cart version;
- normalized constraints, including currency, budget, quantity, and delivery requirement;
- line items sorted by a stable key, with product ID, SKU, product version, quantity, unit price, delivery value, and active state;
- subtotal, shipping, tax, total, and pricing-policy version;
- expiry.

Serialize as canonical UTF-8 JSON with sorted object keys, fixed separators, integer money only, and no floats; hash with SHA-256. Store the canonical inputs and digest. The digest is a consistency binding, not a signature or authorization credential; session and CSRF controls provide request authority.

### Confirmation outcome matrix

| Observed state under the write lock | Result |
|---|---|
| Existing order matches session + preparation + operation key + digest | `idempotent_replay`; return the same receipt. |
| Operation key exists but any tuple component differs | Generic conflict; no order details. |
| Preparation is missing or belongs to another session | Generic rejection; no existence disclosure. |
| Preparation is consumed and its matching order is absent | `HELD`; invariant breach. |
| Preparation is consumed by another operation key | Reject; never create or expose another order. |
| Preparation is expired, invalidated, cart-mutated, quote-stale, digest-mismatched, or constraint-invalid | Reject and persist an owned reason/status; no order. |
| Preparation is pending and fully valid | Commit exactly one order and its snapshots, consume stock, mark preparation consumed, and record the committed attempt. |
| Valid commit has completed and the assigned evaluation fault fires | Persist the post-commit fault event, return `ACK_UNKNOWN` without an order ID, then reconcile by the exact tuple. |

### Transaction sequence

1. Validate request shape and CSRF before opening a database transaction. Derive session from the cookie; accept no client-supplied ownership field.
2. Open one connection with explicit transaction control, foreign keys enabled, and a bounded busy timeout; execute `BEGIN IMMEDIATE`.
3. Look up an existing order using the exact session + preparation + operation tuple. Apply the outcome matrix; never perform an unscoped lookup.
4. Load the preparation through its session owner. Check pending status, server-time expiry, submitted digest, cart owner/version, and one-pending-preparation rule.
5. Re-read all preparation items and current products. Require active products, matching monotonic versions and quote fields, sufficient stock, known delivery, and valid current constraints. Recompute pricing and `preparation-digest-v1`; compare all quoted totals.
6. Insert the order, immutable item snapshots, and confirmation provenance. Atomically decrement each product with a predicate covering ID, version, active state, and sufficient stock; require every update to affect exactly one row.
7. Mark the preparation consumed and insert the committed attempt.
8. Commit. Any error before commit rolls back order, items, stock, attempt, and preparation together.
9. On an integrity race, start a fresh read and return an idempotent replay only for an exact tuple match; otherwise return a generic conflict. Never retry with a new key.
10. Only after commit, run the evaluation-only fault injector. If selected, persist the order-linked fault event in a separate short transaction and return a structured unknown response without the order ID.
11. Reconciliation queries the exact session + preparation + operation tuple and builds the receipt exclusively from durable snapshots. If no exact match exists, return `pending/unknown` or `held`, never inferred success.

## Required tests

### Hour-eight acceptance test — non-negotiable

One public-route integration test must execute:

1. create one session, cart, exact product, valid constraints, and preparation;
2. submit one valid human confirmation with a fixed operation key and assigned post-commit fault;
3. observe an uncertain response containing no order ID;
4. reconcile with the same session, preparation, and operation key;
5. assert exactly one order exists, with unique preparation and operation key;
6. assert the preparation is consumed, stock changed exactly once, and order items/totals equal the prepared snapshot;
7. assert durable UI-route confirmation evidence and one post-commit fault event exist;
8. assert reconciliation returns that exact order and an immutable receipt;
9. repeat confirmation with the same key and assert the same receipt and still one durable order.

The test is local integration proof only. An in-memory mock, direct insertion that bypasses the public route, or an assertion limited to `COUNT(*) = 1` does not satisfy the gate.

### Minimum boundary suite before agent work

- Digest determinism: input ordering does not change the digest; changing any item, quantity, product version, price, delivery value, constraint, total, expiry, cart version, or pricing-policy version does.
- Schema constraints: foreign keys, checks, unique preparation, unique operation key, and one-pending-preparation rule fail closed.
- Same-key replay: exact tuple returns the original order and does not decrement stock twice.
- New-key replay: consumed preparation plus a different key creates no order and reveals no original order ID.
- Key collision: the same operation key with a different preparation or session is a generic conflict with no disclosure.
- Stale preparation: expiry, cart mutation, product deactivation, version/price/delivery/stock change, missing delivery, pricing-policy change, and digest/total tampering create no order.
- Re-preparation: a replacement invalidates or supersedes the prior pending preparation; only the newly confirmed one can commit.
- Session isolation: known cart, preparation, digest, operation key, order, and receipt identifiers from another session all fail closed.
- Concurrency: two real connections confirm concurrently; one order commits and the other returns an exact replay or safe conflict/unknown result.
- Atomic rollback: forced failure during an item insert or stock update leaves no order, no item rows, no stock decrement, and an unconsumed preparation.
- Receipt immutability: later catalogue changes do not alter the receipt.
- Fault boundary: fault configuration is rejected outside evaluation mode; when enabled, the event is later than the committed order and the response contains no order ID.
- Audit semantics: committed, idempotent replay, and owned rejection attempts survive according to the documented policy; rollback does not silently erase a claimed rejection record.

## Risks

1. **Preparation binding is underspecified.** The route and confirmation flow require “the preparation digest,” but the schema defines no such field or algorithm (`ORDERSEAL_BUILD_PLAN.md:201-207,303-317,343-356`). Shipping, tax, expiry, policy version, cart version, and immutable item inputs are not fully bound.
2. **Stock truth is incomplete.** Validation without an atomic decrement permits sequential valid preparations to oversell the synthetic catalogue.
3. **Session scoping is prose-only.** Duplicated `session_id` columns can disagree unless composite ownership is constrained, and an unscoped idempotency lookup can disclose another session's order.
4. **Replay outcomes are ambiguous.** “Return the existing order,” “different operation key cannot create,” and “`ACK_UNKNOWN` never authorizes another new order” do not specify exact tuple matching, collision disclosure, or whether same-key transport retry is allowed (`ORDERSEAL_BUILD_PLAN.md:95-99,257-263,343-356`).
5. **Fault truth is not durable.** The evaluator is expected to derive post-commit acknowledgement loss from SQLite, but no fault-event state exists (`ORDERSEAL_BUILD_PLAN.md:211-224,343-358`). A trajectory log alone cannot be the authoritative order oracle.
6. **Human-confirmation evidence is too weak.** `confirmed_at` proves a timestamp, not the path used. A fixed `confirmation_method` or durable route event is sufficient for this synthetic system; no elaborate signing scheme is needed.
7. **Preparation multiplicity can duplicate intent.** Two pending preparations for one cart can each satisfy the per-preparation uniqueness rule and create two orders.
8. **SQLite scope must be stated.** `BEGIN IMMEDIATE` coordinates writers to one SQLite file. It does not provide distributed exactly-once semantics, and busy/locked behavior must fail closed.
9. **Attempt logging can lie by omission.** Rejected or replay attempt rows disappear if written in a transaction that is rolled back. Define which attempts are authoritative and when they commit.
10. **Clock semantics are absent.** Expiry needs a server-owned UTC epoch representation and an injected deterministic clock for tests; never trust client time.
11. **Peripheral document contradiction:** the build plan consistently requires `IMPROVEMENT_CHANGELOG.md`, while the official review names `CHANGELOG.md` (`ORDERSEAL_BUILD_PLAN.md:68,528,553,578,735`; `OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md:176-178,216-224`). Pick one name before provenance work.

## Recommended plan amendments

1. Replace the broad “exactly-once” claim with the bounded guarantee in this verdict: at-most-once durable effect generally, and exactly one order for the tested accepted-confirmation scenario.
2. Add a **Canonical preparation digest v1** subsection defining the immutable inputs, encoding, hashing, pricing-policy version, cart version, and the rule that the confirmation card renders the same stored snapshot.
3. Add `preparation_digest`, canonical constraints, cart version, immutable preparation items, confirmation provenance, and post-commit fault events to the schema.
4. Add DDL-level ownership, `NOT NULL`, `CHECK`, foreign-key, uniqueness, partial pending-preparation, and delete-policy constraints. State that `PRAGMA foreign_keys=ON` is required per connection.
5. Replace the confirmation prose with the outcome matrix and exact transaction sequence above. Explicitly define same-key replay, new-key rejection, cross-session collision behavior, consumed-without-order handling, lock timeout behavior, and post-integrity-error reread.
6. Decide stock semantics. Recommended: decrement stock atomically in the confirmation transaction; it is the smallest behavior consistent with a synthetic commerce catalogue.
7. Define cart mutation and re-preparation: every cart edit increments its version and invalidates pending preparations; creating a replacement preparation invalidates any prior pending preparation for that cart.
8. Define all quote-changing product updates as version-incrementing, including `active`, stock, delivery, and price. Add a version for shipping/tax logic.
9. Define receipt truth as immutable order snapshots plus durable confirmation/fault evidence. Do not let current catalogue state or agent prose alter a receipt.
10. Expand the hour-eight gate from `durable_order_count == 1` to the exact assertions listed above, while keeping it one focused public-route integration test.
11. Reword “only the browser UI may call” to the enforceable boundary: only the protected confirmation route invokes commit, and the agent has neither that tool nor arbitrary request capability.
12. Resolve the changelog filename mismatch before repository initialization.

## First implementation slice

Build only the deterministic vertical spine in `app/db.py`, `app/domain.py`, the smallest confirmation/status routes in `app/main.py`, and one test module:

1. Create constrained SQLite DDL and a deterministic one-product seed.
2. Create a server session, one cart, one exact item, and normalized constraints.
3. Prepare an immutable quote and `preparation-digest-v1`; renderable response data must come from that stored snapshot.
4. Confirm through the protected route using the transaction contract, including order/item snapshots, stock decrement, preparation consumption, confirmation provenance, and one committed attempt.
5. Inject the deterministic fault only after commit and return `ACK_UNKNOWN` without an order ID.
6. Reconcile by the exact session/preparation/operation tuple and return a receipt derived only from SQLite snapshots.
7. Make the hour-eight integration test pass, then add same-key, new-key, stale, cross-session, concurrency, and rollback boundaries before any model or polished UI work.

This is the smallest truthful spine. The agent, baseline, generic tool loop, full catalogue, evaluation runner, and UI polish should wait until it passes.
