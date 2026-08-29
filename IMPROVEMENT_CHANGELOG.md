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
