# OrderSeal Delivery Review

**Scope:** Product presentation, reproducibility, and deadline delivery
**Evidence reviewed:** `ORDERSEAL_BUILD_PLAN.md` and `OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md`
**Proof layer:** Static planning review only; no application, clean install, browser flow, evaluation run, or video was available to verify.

## Verdict

**CONDITIONAL GO for implementation; HOLD for submission readiness.**

The plan is well aligned with the rubric: it has a specific user, a defensible agent role, a fair baseline, an authoritative oracle, a complete browser story, and explicit deliverables. The official review nevertheless records only a projected recommendation, and the build plan states that implementation has not started (`ORDERSEAL_BUILD_PLAN.md:3-7`; `OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md:79-81,207-214`). No delivery claim is therefore proven yet.

Submission readiness requires direct evidence for all of the following:

1. The hour-eight exactly-once kernel gate passes.
2. The full browser path is keyboard-accessible and visibly reconciles uncertainty.
3. Baseline and OrderSeal runs are frozen, comparable, and oracle-scored.
4. A clean environment reproduces the tested revision from documented commands.
5. The labelled Improvement Changelog, representative trajectories, receipts, and sub-five-minute video are present and inspected.
6. At least two hours remain for final packaging, upload, playback, and recovery.

The strongest product story is not “an AI shopping agent.” It is: **a procurement agent remains useful while consequential authority stays with the human, and ambiguous outcomes are resolved from durable evidence rather than model confidence.**

## Critical Path

The current estimates total 20.5–24.5 focused hours after Gate Zero, while the final 4–5 hour phase also contains 48 live runs, clean-room reproduction, review, artifact inspection, and video production (`ORDERSEAL_BUILD_PLAN.md:641-671`). That leaves no explicit upload or recovery buffer. Use two clocks:

- **Absolute deadline clock:** set `T_submit` with timezone. Freeze features at `T_submit - 20h`, as already required.
- **Focused-work clock:** freeze implementation by focused hour 18.5 even if the absolute freeze is later. The earlier freeze wins.

| Focused time | Required result | Gate / stop rule |
|---:|---|---|
| 0–1 h | Authorized model tool call; non-secret model receipt | Stop if no legitimate provider path exists. Do not build an abstraction. |
| 1–2 h | Provenance files, canonical changelog, minimal executable skeleton | Record kickoff boundary and clean initial revision before adapting donor material. |
| 2–7.5 h | Deterministic kernel and acknowledgement-loss reconciliation | By hour 8, `confirm -> lost acknowledgement -> reconcile -> exactly one durable order` must pass or OrderSeal stops. |
| 7.5–11.5 h | Seven protected tools and one bounded model loop | Live exact-SKU case reaches review-ready state; registry proves no confirmation tool. |
| 11.5–16 h | Fair DirectBuy baseline, oracle, cases, manifests, receipts, metrics | Freeze prompts, schemas, cases, seeds, approval semantics, and metrics before scored runs. |
| 16–18.5 h | One server-rendered browser workflow | Brief through verified receipt works with keyboard-only operation and safe uncertainty handling. Feature work ends here. |
| 18.5–23.5 h | Scored runs, clean reproduction, representative artifacts, final changelog, video | Evidence work only. Preserve failures and do not change metrics or cases. |
| 23.5–25.5 h | Packaging, playback, upload, link verification, recovery | No experiments, features, deployment, or cosmetic refactors. |

Before starting scored runs, estimate their wall time from pilot latency. If the projected run set plus clean-room proof and video cannot finish before the two-hour submission buffer, reduce the case set **before freezing it** as described under Cuts / Fallbacks. Never stop runs selectively or remove failures after observing results.

## UI Acceptance Flow

Use one responsive, server-rendered page with native HTML controls and minimal JavaScript. The acceptance path is:

1. **Purchasing brief**
   - A labelled text area contains the synthetic request.
   - The submit control is a native button and is reachable by keyboard.
   - Validation errors are text, linked to the affected field, and receive focus when submitted.

2. **Investigation and evidence**
   - A chronological status region shows search, inspection, clarification, validation, and preparation without exposing hidden chain-of-thought.
   - Product descriptions render as escaped text and are visibly labelled untrusted catalogue content.
   - Loading and status changes are announced through a restrained `aria-live` status region.

3. **Evidence review card**
   - Show item name, SKU, quantity, observed unit price, stock, delivery estimate, catalogue version, subtotal, shipping, tax, and total.
   - Show each explicit user constraint as `proven`, `not proven`, or `violated`; never turn unknown into pass.
   - Show quote expiry and a short preparation reference. Put technical digests behind optional details.
   - Separate deterministic catalogue/validator facts from model rationale.
   - The human-only **Confirm order** button is enabled only for a current, valid preparation. The card states that the model cannot activate confirmation.

4. **Confirmation**
   - Generate the idempotency key before the first click and retain it across double-click, refresh, and response uncertainty.
   - Disable the button after activation and show progress without implying success.
   - A repeated same-key request must return the original order; a new key cannot consume the same preparation again.

5. **Uncertain acknowledgement**
   - Display: **“Confirmation status is unknown. We are checking the authoritative order record. Do not submit again.”**
   - Do not display an order ID until durable state confirms it.
   - Remove the Confirm action. Offer only automatic reconciliation plus a keyboard-accessible **Check status** fallback.
   - Announce the transition `confirming -> status unknown -> reconciling -> complete/held` to assistive technology.

6. **Verified receipt or held state**
   - Receipt: durable order ID, confirmation time, item snapshots and catalogue versions, quantities, totals, delivery estimate, and **“Verified from authoritative SQLite state.”**
   - Held state: plain-language reason, known facts, unresolved facts, and the safe next action. Never fabricate a receipt when no order exists.
   - Refresh and same-key replay must display the same receipt without creating another order.

7. **Accessibility smoke acceptance**
   - Complete the entire path by keyboard only.
   - Preserve visible focus; use semantic headings, labels, tables/lists, buttons, and status regions.
   - Do not encode pass/fail/unknown by colour alone.
   - Verify reflow at 200% zoom and readable error/status text.
   - Add one deterministic browser smoke check for the primary path. Do not add a component library or custom control framework.

## Reproduction Checklist

`README.md` should be the one canonical reproduction guide. Replace the unproven “one-command” claim with an exact copy/paste sequence; the rubric requires reproducibility, not a bespoke launcher.

### Provenance and environment

- [ ] Final revision is clean, immutable, and printed in the reproduction output.
- [ ] `LICENSE`, `BEFORE_AFTER.md`, `THIRD_PARTY.md`, `.env.example`, `.gitignore`, and `IMPROVEMENT_CHANGELOG.md` exist and are linked from `README.md`.
- [ ] `BEFORE_AFTER.md` records challenge start time, prior-work boundary, and the exact consulted BrowserTransactionBench revision.
- [ ] `THIRD_PARTY.md` records each exercised dependency/source, version, license, and actual use.
- [ ] Exact Python version and exercised direct dependency versions are documented. Include a simple generated lock file if transitive drift remains possible; do not add a dependency manager only for this.
- [ ] No credential, cookie, CSRF token, environment value, personal data, database, or rendered scratch PDF is committed.

### No-key path

- [ ] From a fresh copy, create the virtual environment and install using documented commands.
- [ ] Run the deterministic database reset/seed command; record catalogue seed and digest.
- [ ] Run deterministic and integration tests without a model credential.
- [ ] Start with `.venv/bin/python -m uvicorn app.main:app` rather than a development reload process.
- [ ] Complete a deterministic browser smoke path and record expected terminal/UI output.

The current plan does not define a reset/seed command. Establish one canonical command during implementation and use it in README, local proof, and any CI. Do not make database state depend on a previous run.

### Live evaluation path

- [ ] Clearly mark the step that requires the user to configure an authorized environment variable; never print or inspect its value.
- [ ] Record provider, canonical model ID, settings, case digest, prompt digest, tool-schema digest, source revision, and randomization seed.
- [ ] Run the documented command for both conditions and the frozen repeat count.
- [ ] Confirm that failures and timeouts remain denominator-bearing.
- [ ] Record wall time, available token/cost totals, expected artifact paths, and summary filename.
- [ ] Verify that every score reads the SQLite oracle rather than agent prose.

### Submitted evidence

- [ ] Include an index that links the comparison summary, run manifest, receipts, oracle records, and representative trajectories.
- [ ] Include at least four representative trajectories: DirectBuy normal, DirectBuy acknowledgement-loss/error, OrderSeal normal, and OrderSeal hard case. If one trajectory truthfully covers multiple required behaviours, fewer may suffice, but both agents must be represented.
- [ ] Across the representative set, show tool interactions, feedback/clarification, retry or reconciliation, errors/timeouts or held behaviour, and human checkpoints.
- [ ] Extend trajectory events to include retry, error, timeout, clarification, held resolution, and oracle result. Continue excluding hidden chain-of-thought and session material.
- [ ] Run a final secret/session-material inspection over logs and submitted artifacts.
- [ ] Re-run the guide in a separate clean directory at the exact final revision and preserve the command log as the reproduction receipt.

## Improvement Changelog Protocol

Use exactly one file: **`IMPROVEMENT_CHANGELOG.md`**. The official review alternates between `CHANGELOG.md` and “Improvement Changelog,” while the build plan consistently defines the clearer filename (`ORDERSEAL_BUILD_PLAN.md:68,520-553`; `OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md:176-178,216-224`). Do not maintain two logs.

Create it in the first provenance revision and append an entry when an experiment resolves, not at submission time. Each entry records:

1. Date/time and source revision.
2. User or safety problem being tested.
3. Hypothesis and intervention.
4. Frozen pilot cases, case digest, prompt digest, tool-schema digest, model/settings, and seed.
5. Evidence links to receipts, trajectories, and oracle output.
6. Primary metric and relevant countermetrics, including human effort.
7. Observed result, including failures and uncertainty.
8. Decision: `kept`, `modified`, or `removed`.
9. Lesson and resulting plan/product change.

Rules:

- Freeze the scored configuration after the pilot; scored results never justify rewriting success criteria.
- Record only meaningful product/agent experiments, not routine commits or cosmetic changes.
- Include at least one genuinely removed experiment and its evidence. Do not invent one after the fact.
- If no honest removed experiment exists by the absolute feature freeze, run one bounded, unscored pilot on a small frozen subset only if it fits within 20 minutes; otherwise state that the requirement is unmet rather than fabricating evidence.
- A fair example, if it actually occurs, is an early DirectBuy prompt without explicit history reconciliation that is replaced after an acknowledgement-loss pilot. The submitted baseline must retain the reasonable reconciliation instruction.

## Five-Minute Video Outline and Demo Script

Target **4:50**, leaving ten seconds of encoding/platform margin. Record the tested local revision. Rehearse once, verify audio and text legibility, then play the exported file end to end and confirm duration before upload. Label any replayed/captured run; never present projected metrics as measured.

| Time | Picture / action | Narration target |
|---:|---|---|
| 0:00–0:20 | Synthetic keyboard request | Procurement coordinators must satisfy budget and delivery constraints; a lost success response can cause an unsafe retry. |
| 0:20–0:40 | One-service diagram and tool list | The model investigates and reconciles, the browser human confirms, and SQLite—not model prose—defines what happened. |
| 0:40–1:25 | Enter brief; show evidence timeline and review card | Point out SKU, price, stock, delivery, version, constraints, and total. Product descriptions are untrusted evidence. |
| 1:25–1:45 | Confirmation card | State that the agent has no confirmation tool. Read the key facts and click Confirm once. |
| 1:45–2:10 | Deterministic acknowledgement-loss state | The commit may have succeeded, but the response is intentionally suppressed. The UI does not offer a second confirmation. |
| 2:10–2:35 | Reconciliation and receipt | Query authoritative state, show exactly one durable order, and display the SQLite-verified receipt. Refresh/replay returns the same order. |
| 2:35–3:10 | Hard-case trajectory | Show prompt injection plus price change; the system treats text as untrusted, revalidates, and either gets a fresh human confirmation or holds safely. |
| 3:10–3:35 | DirectBuy baseline | Same model, catalogue, cases, limits, history access, and explicit prompt-level reconciliation; explain structural versus prompted safety. |
| 3:35–4:05 | Frozen results | Lead with safe completion, then duplicate/unauthorized/constraint/false-claim rates, reconciliation, human effort, latency, cost, and failures. |
| 4:05–4:25 | Improvement Changelog | Show one retained and one genuinely removed experiment, their evidence, and the largest measured lesson. |
| 4:25–4:42 | README and artifact index | Show exact clean-install commands, final revision, representative trajectories, and receipts. |
| 4:42–4:50 | Limits slide | Synthetic/local evidence only; no real payment, production-security, or universal model-behaviour claim. |

If the live hard case is too slow or flaky for recording, use its already-generated sanitized trajectory and receipt, visibly labelled **recorded run**. Do not rerun until a favourable outcome appears.

## Cuts / Fallbacks

### Cut now without losing rubric value

- Hosted deployment, unless all local evidence is complete and it fits inside a separate two-hour budget.
- Streaming, React, animation, design systems, custom controls, WebSockets, queues, workers, provider abstractions, multi-agent orchestration, and external commerce integrations.
- Broad catalogue content; keep a deterministic catalogue just large enough to exercise the frozen cases.
- More than one page, one test module initially, or a bespoke setup wrapper. Native HTML and exact README commands are enough.
- A third evaluation repeat.
- Full raw artifact publication when size obscures review. Preserve the complete local run set, but submit an index, comparison, receipts, and representative sanitized trajectories.
- Cosmetic polish after the browser flow is clear, accessible, and stable.

Do **not** cut structural human confirmation, the uncertain state, authoritative reconciliation, the fair baseline, denominator-bearing failures, changelog evidence, representative trajectories, clean reproduction, or the video. Those directly protect rubric points.

### Deadline fallback: reduce from 12 to 10 cases

The official guidance recommends ten or more cases; twelve is a planning choice, not a stated rubric requirement (`OFFICIAL_PDF_AND_CLAUDE_OPUS5_REVIEW.md:30-41`). If projected evaluation time threatens the submission buffer, consolidate before the frozen manifest:

- Combine brand/synonym ambiguity with currency/pack-size/quantity ambiguity into one clarification case.
- Combine missing delivery information with impossible delivery date into one delivery-evidence case.

Then run 10 cases × 2 conditions × 2 repeats = 40 live scored runs. Preserve the hard case, acknowledgement loss, prompt injection, stale price, comparison-only/no-order, and double-click coverage. Disclose the reduction and rationale. Never reduce after seeing results.

### Technical fallbacks

- Gate Zero unresolved after one hour: stop; select an authorized provider path. Do not request credentials or assume an interactive subscription is a batch API.
- Exactly-once kernel not green by focused hour eight: switch to RepoWorth. Do not weaken the invariant.
- Model integration unreliable: keep one provider and the smallest bounded tool loop; reduce optional reasoning/UI detail, not authority controls.
- Hosting exceeds its separate budget: abandon hosting and submit the clean local reproduction plus video.
- Video live demo flaky: show a sanitized, pre-recorded run with its receipt and revision, explicitly labelled.
- Evaluation shows no advantage: report it honestly and explain the structural tradeoff; do not weaken the baseline or change metrics.

## Recommended Plan Amendments

1. **Add a submission-readiness gate.** Require exact paths/status for the Gate Zero receipt, final revision, hour-eight test, browser smoke evidence, run manifest, comparison, representative trajectories, clean-room log, changelog, video, and secret scan.
2. **Make the deadline executable.** Record `T_submit` and timezone; use the earlier of `T_submit - 20h` and focused hour 18.5 as feature freeze; reserve two untouched hours for upload/recovery.
3. **Resolve the changelog name.** Replace every `CHANGELOG.md` reference with `IMPROVEMENT_CHANGELOG.md` and link it from README.
4. **Specify the evidence card and receipt.** Add the exact fields, provenance labels, unknown/violated states, expiry, human-only action, and SQLite-verification wording defined above.
5. **Specify `ACK_UNKNOWN` presentation.** No order ID before proof, no second Confirm action, explicit authoritative check, and a clear held result on contradiction.
6. **Add concrete accessibility acceptance.** Keyboard-only completion, labels, focus, semantic status announcements, non-colour state cues, 200% reflow, and one deterministic browser smoke check.
7. **Make README canonical.** Add exact runtime/dependencies, deterministic reset/seed, no-key and live-key paths, expected output, runtime/cost, artifact locations, and the exact final revision. Drop the bespoke “one-command” requirement unless it naturally remains one line.
8. **Add a pre-run fairness manifest.** Bind revision, prompts, schemas, cases, seeds, model/settings, time/step/retry limits, fault assignment, and metric definitions before scoring. Define equivalent approval-event and human-time semantics for DirectBuy and OrderSeal.
9. **Complete the trajectory contract.** Add retry, error, timeout, clarification, held-resolution, and oracle-result events; define the representative submitted set and final sanitization check.
10. **Budget the evaluation before running it.** Use pilot latency to project the full run set; choose 12 or the disclosed 10-case fallback before freeze, then preserve every result.
11. **Add the timed video storyboard.** Require final-revision identity, replay labels, local playback, duration verification, and an explicit limitations close.
12. **Keep hosting out of the critical path.** Deployment begins only after every local deliverable passes and never consumes the submission buffer.

These amendments tighten delivery without adding architecture. The lazier viable product is one accessible server-rendered page, one deterministic SQLite kernel, one bounded model loop, one fair baseline, and evidence that a judge can reproduce.
