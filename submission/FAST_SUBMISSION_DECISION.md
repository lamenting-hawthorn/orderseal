# OrderSeal fast submission decision

Decision: **GO for a hackathon demo/submission package; HOLD production and strict preregistered-evaluation claims.**

This lower release bar was explicitly chosen after the strict review veto because submission time is limited. It does not erase or rewrite that review.

## Safe claims

- The synthetic local application works through review, protected confirmation, acknowledgement uncertainty, authoritative reconciliation, and receipt display.
- Local checks pass, including adversarial coverage for a malformed effect database, failed-row denominator handling, and DirectBuy no-retry during reconciliation.
- A historical sealed provider run contains all 48 frozen assignments and can be rescored offline. Its descriptive result is DirectBuy 12/24 versus OrderSeal 19/24, a paired difference of +29.17 percentage points.
- The exporter verifies the execution tree, scoring report, and scoring seal before producing sanitized evidence.

## Claims still on HOLD

- The historical provider run is not presented as strictly preregistered: its included record says `scored_execution_authorized=false`, and the hardened scorer postdates the run.
- No staging, production, real-payment, deployment, hosted-video, upload, or external-submission proof exists.
- Evaluation mode must remain loopback-only; that boundary is documented but not enforced as a deployment control.
- Provider cost, wall-clock latency, real human time, and reliable clarification-answer counts are unavailable.

The strict findings remain preserved in [`FINAL_VETO.md`](FINAL_VETO.md). This decision accepts those residual evidence limitations for the hackathon package only; it does not authorize provider reruns or external submission.
