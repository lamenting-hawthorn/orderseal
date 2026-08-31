from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from app.agent import (
    OPENROUTER_HEALTH_CHECK_TOOL,
    OPENROUTER_REQUIRED_PARAMETERS,
    AgentState,
    EmptyArguments,
    OpenRouterCaller,
    RunBudget,
    ToolContext,
    ToolProgram,
    run_tool_program,
)
from app.domain import canonical_json, digest
from evals.protocol import (
    PROVIDER_BASE_URL,
    PROVIDER_CANONICAL_MODEL_ID,
    PROVIDER_MODEL_ID,
    UPSTREAM_PROVIDER,
    write_immutable,
)
from evals.runner import PROJECT_ROOT, _load_local_env

PROBE_COUNT = 8
RECEIPT_PATH = PROJECT_ROOT / "route-qualification-openai-gpt-5-6-luna.json"
FAILED_RECEIPT_PATH = (
    PROJECT_ROOT / "route-qualification-openai-gpt-5-6-luna-failed.json"
)


def _health_check(_context: ToolContext, _arguments: BaseModel) -> dict[str, object]:
    return {"status": "ok"}


HEALTH_PROGRAM = ToolProgram(
    schemas=[OPENROUTER_HEALTH_CHECK_TOOL],
    argument_models={"health_check": EmptyArguments},
    handlers={"health_check": _health_check},
    completion=lambda _context, _result: None,
    stopped_reason="route_qualification_complete",
    stopped_status="complete",
)


def qualify_route(caller: OpenRouterCaller) -> dict[str, Any]:
    preflight = caller.preflight(set(OPENROUTER_REQUIRED_PARAMETERS))
    probes: list[dict[str, object]] = []
    for index in range(1, PROBE_COUNT + 1):
        budget = RunBudget()
        outcome = run_tool_program(
            ToolContext(None, AgentState(), lambda: 0),
            [
                {
                    "role": "user",
                    "content": "Call health_check exactly once, then respond DONE after its result.",
                }
            ],
            caller,
            HEALTH_PROGRAM,
            budget=budget,
        )
        passed = (
            outcome.status == "complete"
            and outcome.reason == "route_qualification_complete"
            and budget.model_responses == 2
            and budget.tool_calls == 1
            and budget.models <= {PROVIDER_MODEL_ID, PROVIDER_CANONICAL_MODEL_ID}
            and len(outcome.trajectory) == 1
            and outcome.trajectory[0].get("tool") == "health_check"
            and outcome.trajectory[0].get("outcome") == "ok"
        )
        probes.append(
            {
                "probe": index,
                "passed": passed,
                "status": outcome.status,
                "reason": outcome.reason,
                "model_responses": budget.model_responses,
                "tool_calls": budget.tool_calls,
                "returned_models": sorted(budget.models),
            }
        )
    body = {
        "schema": "orderseal-route-qualification-v1",
        "proof_layer": "real_provider_generic_unscored",
        "model": PROVIDER_MODEL_ID,
        "canonical_model": PROVIDER_CANONICAL_MODEL_ID,
        "provider": UPSTREAM_PROVIDER,
        "probe_count": PROBE_COUNT,
        "preflight": preflight,
        "probes": probes,
        "all_passed": all(probe["passed"] is True for probe in probes),
        "scored_cases_used": False,
    }
    return {**body, "receipt_digest": digest("orderseal-route-qualification-v1", body)}


def main() -> None:
    _load_local_env()
    caller = OpenRouterCaller(
        base_url=PROVIDER_BASE_URL,
        model=PROVIDER_MODEL_ID,
        api_key=os.environ["ORDERSEAL_API_KEY"],
        provider_slug=UPSTREAM_PROVIDER,
        require_parameters=False,
    )
    receipt = qualify_route(caller)
    output_path = RECEIPT_PATH if receipt["all_passed"] is True else FAILED_RECEIPT_PATH
    write_immutable(output_path, f"{canonical_json(receipt)}\n".encode())
    print(canonical_json(receipt))
    if receipt["all_passed"] is not True:
        raise ValueError("route qualification failed")


if __name__ == "__main__":
    main()
