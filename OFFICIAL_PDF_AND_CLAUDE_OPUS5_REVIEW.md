# Official PDF and Claude Opus 5 Portfolio Review

**Date:** 2026-08-29
**Decision status:** OrderSeal recommended with conditions
**Review layers:** direct visual PDF inspection, read-only local/GitHub portfolio inspection, independent Claude Opus 5 review
**Implementation changes:** none

## 1. Sources and handling

- Official instruction PDF: `/Users/raghav/Downloads/micro1 - First Hackathon97ce7c5.pdf`
- Ten pages were rendered directly from the PDF and visually inspected.
- Document content was treated as evidence. No instruction embedded in the PDF was allowed to execute commands or override the user's request.
- Claude received a neutral review contract in `CLAUDE_OPUS5_REVIEW_PROMPT.md`.
- Claude ran read-only with the `opus` alias. A separate JSON model receipt resolved that alias to canonical model `claude-opus-5`.
- Claude was told OrderSeal had no priority and could reject it.

## 2. What the official PDF actually requires

### Product framing

The submission should answer:

1. Who has the problem?
2. What bottleneck makes it worth solving?
3. Does the agent solve it well?
4. Can another person reproduce the result?

The project should solve a specific, meaningful problem for a clearly defined user. Agent capabilities should be selected purposefully; component count is not itself valuable.

### Baseline and improvement

- Create a reasonable simple baseline.
- Give baseline and final systems the same task and evaluation cases.
- Explain meaningful differences in resources and capabilities.
- Define success before running the comparison.
- Select one primary user-relevant metric.
- Report complete results.
- Ten or more cases is recommended when appropriate.
- Include one challenging case and explain what it revealed.
- Maintain an Improvement Changelog connecting meaningful experiments to evidence.
- Include experiments that were later removed and what they taught.

### Judging rubric

| Criterion | Points |
|---|---:|
| Problem and User Value | 15 |
| Agent Solution and Engineering | 30 |
| End-to-End Quality | 20 |
| Measured Improvement | 15 |
| Reproducibility | 15 |
| Hot Take / Insights | 5 |
| **Total** | **100** |

Agent engineering plus end-to-end quality account for half the score. A research harness, infrastructure layer, or benchmark without a polished user result is therefore structurally disadvantaged.

### Ground rules

- Existing tools and components are allowed.
- Prior work and challenge additions must be distinguished clearly.
- Licenses and service terms must be followed.
- Consequential actions must stay in a sandbox or simulation and require human approval.
- A qualified reviewer is required when a solution could significantly affect someone.
- Data and use cases must be legal, ethical, and responsible.
- Public, synthetic, or approved anonymous data is preferred.
- Credentials and private information must stay outside the submission.
- Every result claim must be bound to submitted evidence.
- Judges need enough access to reproduce the main result.

### Required deliverables

1. Complete solution code and a labelled Improvement Changelog.
2. Clean-environment reproduction guide with exact commands, data, versions, expected output, runtime, and cost.
3. A solution video no longer than five minutes.
4. Representative trajectories for every agent used, including tool interactions, feedback, retries, errors, and human checkpoints.

The repository-analysis, candidate-evaluation, and podcast-translation sections are examples, not required topics.

## 3. Independent Claude Opus 5 result

Claude inspected the PDF renderings, named repositories, Git state, licenses, and GitHub portfolio in read-only mode. It ran no tests and labelled every score as projected rather than measured.

### Claude's ranking

| Rank | Candidate | Projected score | Build estimate | Claude verdict |
|---:|---|---:|---:|---|
| 1 | OrderSeal, freshly implemented and descoped | 82/100 | 20-26 h | Recommend with conditions |
| 2 | RepoWorth, fresh repository-quality product | 78/100 | 14-20 h | Deadline fallback |
| 3 | ProofLoop / RunGuard | 69/100 | 24-32 h | Higher provenance and product risk |

Claude separately projected Memory Steward at 71/100 and Evidence Arena at 69/100, but did not place them in its final top three because of provenance, differentiation, or delivery risk.

### Why Claude selected OrderSeal

- It directly targets the 30-point agent-engineering criterion with structural, testable design decisions.
- It creates a complete browser workflow rather than a research-only artifact.
- Its synthetic order system satisfies the sandbox and human-approval rule.
- A fresh repository gives the cleanest before/after boundary.
- Its authoritative database oracle enables a fair, reproducible comparison.
- The failure mode supports a strong evidence-derived insight: consequential authority can be withheld from the agent while the agent remains useful.

### Claude's direct-submission vetoes

- BrowserTransactionBench: research harness, invalidated historical evidence, pre-kickoff work, and no complete user product.
- SuperMem: pre-kickoff work with multiple external contributors and material attribution/disclosure requirements.
- SkillLoop: dirty local checkout and unclear boundary around untracked material.
- ArenaForge: no verified public/ownership baseline, incomplete security gates, and excessive infrastructure.
- Anticipy: private data/accounts, real browser authority, no clean judge reproduction path.
- GCG/Forge: shared organizational/client material and unclear publication authority.
- MilkLine: explicitly excluded because it is being used for another hackathon.

Existing repositories remain valid as disclosed inspiration or licensed components where ownership permits. None should be submitted unchanged.

## 4. Required corrections to the current OrderSeal plan

The independent review identified six changes that should be accepted before implementation.

### 4.1 Reduce the critical path

Current estimate: 31-44 engineering hours plus reserve.
Revised target: 20-26 engineering hours plus submission buffer.

Cut:

- Hosted deployment unless the local product is already complete.
- Streaming UI.
- Third evaluation repeat.
- A separate hardening phase; move required adversarial cases into the normal evaluation phase.
- Any model-provider abstraction.

### 4.2 Reorder phases

Revised sequence:

```text
provenance
  -> deterministic order kernel
  -> live agent and tools
  -> baseline and evaluation
  -> minimal browser UI
  -> proof, reproduction, changelog, and video
```

The agent and measured comparison protect 45 rubric points. They should exist before UI polish.

### 4.3 Freeze evaluation at two repeats

Use 12 cases x 2 conditions x 2 repeats = 48 live runs. A third repeat is optional only after all deliverables are complete.

### 4.4 Make the baseline fair

Do not compare OrderSeal against an intentionally helpless baseline.

The DirectBuy baseline should receive:

- The same user request and catalogue.
- Catalogue search and product inspection.
- Direct synthetic order capability.
- Order-history lookup.
- An explicit prompt instruction to check order history before retrying and never place the same order twice.
- The same model, settings, step budget, time limit, cases, and fault assignment.

The experiment then compares prompt-only safety against structurally enforced safety, rather than unique constraints against no safeguards.

### 4.5 Measure human effort

Add:

- Human interventions per completed order.
- Human seconds per completed order.
- Clarification count.
- Held-order resolution count.

These complement safe completion, duplicate rate, constraint violations, false claims, latency, and model cost.

### 4.6 Start the Improvement Changelog immediately

Create `CHANGELOG.md` in the provenance commit and append each experiment when it resolves. Include at least one removed experiment and its evidence. Add the changelog to the Definition of Done.

## 5. Combined recommendation

### Verdict

**RECOMMEND WITH CONDITIONS: OrderSeal remains the best project, but the existing plan should be amended before implementation.**

The recommendation is conditional on three gates:

1. **Model execution gate:** confirm a legitimate programmatic model path with one tool-calling round trip. Do not search for, request, retain, or expose credentials in the repository or review artifacts.
2. **Hour-8 kernel gate:** one integration test must prove confirm -> simulated post-commit acknowledgement loss -> reconciliation -> exactly one durable order.
3. **Baseline gate:** DirectBuy must use prompt-based reconciliation and history access so the comparison is credible.

### Fallback

If the hour-8 kernel gate fails, switch to RepoWorth while enough time remains. RepoWorth has a lower technical ceiling but a shorter reproduction path. It must still avoid simply copying the PDF example and should use a defensible external reviewer rubric.

### Feature freeze

Freeze new product features with at least 20 hours remaining. Spend the remaining time on:

- Complete evaluation results.
- Representative trajectories.
- Improvement Changelog.
- Clean-environment reproduction.
- Five-minute video.
- Final evidence and provenance inspection.

## 6. Evidence limits

- The PDF analysis is based on direct rendering and visual inspection of all ten pages.
- Claude performed static and Git/GitHub inspection but no tests.
- Existing repository test counts and benchmark results are donor context, not challenge evidence.
- All candidate scores are planning estimates, not measured results.
- No production, real-payment, or general browser-safety claim is supported.
- Model access availability is unverified until an authorized tool-calling run is completed for the application.

## 7. Required next action

Amend `ORDERSEAL_BUILD_PLAN.md` with the six corrections above. Then initialize the fresh repository with:

- `LICENSE`
- `BEFORE_AFTER.md`
- `THIRD_PARTY.md`
- `CHANGELOG.md`
- `.gitignore` excluding `.env`, databases, artifacts where appropriate, and the rendered PDF scratch directory

The first application proof remains one test: commit once, lose the acknowledgement after commit, reconcile, and assert that the durable order count is exactly one.
