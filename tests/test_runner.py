from __future__ import annotations

import inspect
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from app.agent import (
    MAX_MODEL_RESPONSES,
    AgentState,
    ModelTurn,
    ProviderError,
    RunBudget,
    ToolContext,
    candidate_program,
    run_tool_program,
)
from app.baseline import run_direct_buy
from app.domain import record_evaluation_approval
from evals.policy import candidate_policy_for_case
from evals.preregister import MODEL_ID, build_preregistration
from evals.protocol import build_assignments, load_cases
from evals.runner import (
    RunnerSettings,
    _run_assignment,
    _shared_parameters,
    frozen_provider_settings,
)


class SequenceCaller:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = deque(turns)
        self.calls = 0

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout_seconds: float,
    ) -> ModelTurn:
        del messages, tools, timeout_seconds
        self.calls += 1
        return self.turns.popleft()


def tool_turn(name: str, arguments: str, number: int) -> ModelTurn:
    return ModelTurn(
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"runner-call-{number}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        },
        model="scripted-model",
        usage={"total_tokens": 5},
    )


def candidate_action_turns() -> list[ModelTurn]:
    return [
        tool_turn("inspect_product", '{"sku":"KB-ERG-001"}', 1),
        tool_turn("set_cart", '{"sku":"KB-ERG-001","quantity":2}', 2),
        tool_turn("validate_cart", "{}", 3),
        tool_turn("prepare_order", "{}", 4),
    ]


def candidate_turns() -> list[ModelTurn]:
    return [*candidate_action_turns(), claim_turn("complete", "committed")]


def directbuy_turns() -> list[ModelTurn]:
    return [
        tool_turn("inspect_product", '{"sku":"KB-ERG-001"}', 1),
        tool_turn("set_cart", '{"sku":"KB-ERG-001","quantity":2}', 2),
        tool_turn("place_order", "{}", 3),
        claim_turn("complete", "committed"),
    ]


def claim_turn(
    terminal_state: str,
    effect_claim: str,
    *,
    reconciled: bool = False,
    model: str = "scripted-model",
) -> ModelTurn:
    return ModelTurn(
        message={
            "role": "assistant",
            "content": (
                f'{{"terminal_state":"{terminal_state}",'
                f'"effect_claim":"{effect_claim}",'
                f'"reconciled":{str(reconciled).lower()}}}'
            ),
        },
        model=model,
        usage={"total_tokens": 3},
    )


def test_oracle_blind_paired_assignments_use_fresh_databases(tmp_path: Path) -> None:
    settings = RunnerSettings(
        "scripted", "scripted-model", "https://example.invalid/v1"
    )
    case = load_cases()[0]
    assignments: list[dict[str, Any]] = [
        {
            "run_id": "paired-c01-directbuy",
            "pair_id": "C01-R1",
            "case_id": "C01",
            "repeat": 1,
            "condition": "directbuy",
        },
        {
            "run_id": "paired-c01-orderseal",
            "pair_id": "C01-R1",
            "case_id": "C01",
            "repeat": 1,
            "condition": "orderseal",
        },
    ]
    output = tmp_path / "paired"
    output.mkdir()
    shared = _shared_parameters(assignments[0], case, settings)
    from app.domain import digest

    shared_digest = digest("orderseal-pair-parameters-v1", shared)

    def callers(assignment: dict[str, Any]) -> SequenceCaller:
        turns = (
            directbuy_turns()
            if assignment["condition"] == "directbuy"
            else candidate_turns()
        )
        return SequenceCaller(turns)

    receipts = [
        _run_assignment(
            output,
            index,
            assignment,
            case,
            shared_digest,
            callers,
            settings,
        )
        for index, assignment in enumerate(assignments, start=1)
    ]

    assert {receipt["shared_parameter_digest"] for receipt in receipts} == {
        shared_digest
    }
    assert all(receipt["denominator_included"] for receipt in receipts)
    assert all(
        receipt["structured_final_claim"]["effect_claim"] == "committed"
        for receipt in receipts
    )
    assert all(receipt["session_count"] == 1 for receipt in receipts)
    assert not list(output.glob("**/oracle.json"))
    for assignment in assignments:
        database_path = output / str(assignment["run_id"]) / "state.sqlite3"
        with sqlite3.connect(database_path) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM orders"
            ).fetchone()[0] + connection.execute(
                "SELECT COUNT(*) FROM directbuy_orders"
            ).fetchone()[0] == 1


def test_provider_failure_is_not_retried_or_removed_from_denominator(
    tmp_path: Path,
) -> None:
    class FailingCaller:
        calls = 0

        def __call__(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            timeout_seconds: float,
        ) -> ModelTurn:
            del messages, tools, timeout_seconds
            self.calls += 1
            raise ProviderError("synthetic_provider_failure")

    caller = FailingCaller()
    assignment = {
        "run_id": "failed-c01-orderseal",
        "pair_id": "C01-R1",
        "case_id": "C01",
        "repeat": 1,
        "condition": "orderseal",
    }
    output = tmp_path / "failed"
    output.mkdir()
    receipt = _run_assignment(
        output,
        1,
        assignment,
        load_cases()[0],
        "a" * 64,
        lambda _assignment: caller,
        RunnerSettings("scripted", "failure-model", "https://example.invalid/v1"),
    )

    assert caller.calls == 1
    assert receipt["run_status"] == "failed"
    assert receipt["error_classification"] == "provider_error"
    assert receipt["denominator_included"] is True
    assert receipt["structured_final_claim"] is None
    assert (output / str(assignment["run_id"]) / "receipt.json").exists()


def test_candidate_reconciliation_failure_is_not_reported_complete(
    tmp_path: Path,
) -> None:
    class FailsAfterTurns(SequenceCaller):
        def __call__(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            timeout_seconds: float,
        ) -> ModelTurn:
            if not self.turns:
                self.calls += 1
                raise ProviderError("reconciliation_failed")
            return super().__call__(messages, tools, timeout_seconds)

    case = load_cases()[7]
    assignment: dict[str, Any] = {
        "run_id": "failed-c08-orderseal",
        "pair_id": "C08-R1",
        "case_id": "C08",
        "repeat": 1,
        "condition": "orderseal",
    }
    output = tmp_path / "candidate-reconciliation"
    output.mkdir()
    receipt = _run_assignment(
        output,
        1,
        assignment,
        case,
        "b" * 64,
        lambda _assignment: FailsAfterTurns(candidate_action_turns()),
        RunnerSettings("scripted", "scripted-model", "https://example.invalid/v1"),
    )

    assert receipt["run_status"] == "failed"
    assert receipt["error_classification"] == "provider_error"
    assert receipt["effect_observation"] == "committed"
    assert receipt["structured_final_claim"] is None
    assert receipt["fault_event_count"] == 1


def test_directbuy_records_external_fault_before_reconciliation_failure(
    tmp_path: Path,
) -> None:
    class CrashesAfterTurns(SequenceCaller):
        def __call__(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            timeout_seconds: float,
        ) -> ModelTurn:
            if not self.turns:
                self.calls += 1
                raise RuntimeError("unexpected_reconciliation_crash")
            return super().__call__(messages, tools, timeout_seconds)

    case = load_cases()[7]
    assignment: dict[str, Any] = {
        "run_id": "failed-c08-directbuy",
        "pair_id": "C08-R1",
        "case_id": "C08",
        "repeat": 1,
        "condition": "directbuy",
    }
    output = tmp_path / "directbuy-reconciliation"
    output.mkdir()
    receipt = _run_assignment(
        output,
        1,
        assignment,
        case,
        "c" * 64,
        lambda _assignment: CrashesAfterTurns(directbuy_turns()[:-1]),
        RunnerSettings("scripted", "scripted-model", "https://example.invalid/v1"),
    )

    assert receipt["run_status"] == "failed"
    assert receipt["error_classification"] == "RuntimeError"
    assert receipt["effect_observation"] == "committed"
    assert receipt["fault_event_count"] == 1
    assert receipt["execution_terminal"]["reason"] == "runner_exception"
    usage_path = output / str(assignment["run_id"]) / "usage.json"
    trajectory_path = output / str(assignment["run_id"]) / "trajectory.jsonl"
    assert '"total_tokens":15' in usage_path.read_text()
    assert trajectory_path.read_text().count('"event":"tool_result"') == 3


def test_c02_answer_is_not_injected_without_a_question(tmp_path: Path) -> None:
    no_question = ModelTurn(
        message={"role": "assistant", "content": "No question asked."},
        model="scripted-model",
        usage={"total_tokens": 2},
    )
    assignment: dict[str, Any] = {
        "run_id": "c02-no-question-directbuy",
        "pair_id": "C02-R1",
        "case_id": "C02",
        "repeat": 1,
        "condition": "directbuy",
    }
    output = tmp_path / "clarification"
    output.mkdir()
    receipt = _run_assignment(
        output,
        1,
        assignment,
        load_cases()[1],
        "d" * 64,
        lambda _assignment: SequenceCaller(
            [no_question, claim_turn("held", "not_committed")]
        ),
        RunnerSettings("scripted", "scripted-model", "https://example.invalid/v1"),
    )

    assert receipt["effect_observation"] == "not_committed"
    assert receipt["structured_final_claim"]["effect_claim"] == "not_committed"
    assert receipt["execution_terminal"]["reason"] == "clarification_not_requested"
    assert receipt["approval_event_count"] == 0
    assert receipt["session_count"] == 1


def test_candidate_approval_binds_each_reviewed_quote(tmp_path: Path) -> None:
    assignment: dict[str, Any] = {
        "run_id": "c06-orderseal-review-refresh",
        "pair_id": "C06-R1",
        "case_id": "C06",
        "repeat": 1,
        "condition": "orderseal",
    }
    output = tmp_path / "approval-binding"
    output.mkdir()
    turns = [
        *candidate_action_turns(),
        *candidate_action_turns(),
        claim_turn("complete", "committed"),
    ]
    receipt = _run_assignment(
        output,
        1,
        assignment,
        load_cases()[5],
        "e" * 64,
        lambda _assignment: SequenceCaller(turns),
        RunnerSettings("scripted", "scripted-model", "https://example.invalid/v1"),
    )

    database_path = output / str(assignment["run_id"]) / "state.sqlite3"
    with sqlite3.connect(database_path) as connection:
        approval_digests = [
            row[0]
            for row in connection.execute(
                "SELECT displayed_cart_digest FROM evaluation_approval_events ORDER BY rowid"
            ).fetchall()
        ]
        preparation_digests = [
            row[0]
            for row in connection.execute(
                "SELECT preparation_digest FROM preparations ORDER BY created_at_epoch, rowid"
            ).fetchall()
        ]
    assert receipt["run_status"] == "completed"
    assert len(set(approval_digests)) == 2
    assert approval_digests == preparation_digests


def test_returned_model_drift_fails_closed(tmp_path: Path) -> None:
    assignment: dict[str, Any] = {
        "run_id": "c01-model-drift-orderseal",
        "pair_id": "C01-R1",
        "case_id": "C01",
        "repeat": 1,
        "condition": "orderseal",
    }
    output = tmp_path / "model-drift"
    output.mkdir()
    turns = [
        *candidate_action_turns(),
        claim_turn("complete", "committed", model="different-model"),
    ]
    receipt = _run_assignment(
        output,
        1,
        assignment,
        load_cases()[0],
        "f" * 64,
        lambda _assignment: SequenceCaller(turns),
        RunnerSettings("scripted", "scripted-model", "https://example.invalid/v1"),
    )

    assert receipt["run_status"] == "failed"
    assert receipt["error_classification"] == "model_identity_mismatch"
    assert receipt["returned_models"] == ["different-model", "scripted-model"]


def test_runner_source_does_not_import_expectations_or_scorer() -> None:
    from evals import runner

    source = inspect.getsource(runner)
    assert "load_expectations" not in source
    assert "evals.score" not in source
    assert "oracle.json" not in source


def test_directbuy_receives_non_demo_policy_and_case_prompt(tmp_path: Path) -> None:
    from app import db

    class PromptCapture:
        system_prompt = ""

        def __call__(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            timeout_seconds: float,
        ) -> ModelTurn:
            del tools, timeout_seconds
            self.system_prompt = str(messages[0]["content"])
            return ModelTurn(message={"role": "assistant", "content": "Stop."})

    database_path = tmp_path / "directbuy-policy.sqlite3"
    db.reset(database_path, db.EVAL_SEED_NAME)
    caller = PromptCapture()
    policy = candidate_policy_for_case("C04")
    case = load_cases()[3]
    with db.connect(database_path) as connection:
        run = run_direct_buy(
            connection,
            case["request"],
            caller,
            run_id="directbuy-policy-c04",
            approval_provider=lambda session_id, snapshot: record_evaluation_approval(
                connection,
                run_id="directbuy-policy-c04",
                condition="directbuy",
                session_id=session_id,
                displayed_cart_digest=snapshot["displayed_cart_digest"],
                decision="rejected",
                actor="scripted_evaluator",
                displayed_at_monotonic_ms=1_000,
                decided_at_monotonic_ms=1_200,
                server_received_at_epoch=1_800_000_000,
            ),
            clock=lambda: 1_800_000_000,
            policy=policy,
        )

    assert run.outcome.status == policy.terminal_without_effect
    assert policy.source_digest is not None
    assert policy.source_digest in caller.system_prompt
    assert "KB-ALT-002" in caller.system_prompt
    assert "KB-OOS-006" in caller.system_prompt


def test_run_budget_is_shared_across_program_invocations(tmp_path: Path) -> None:
    from app import db

    database_path = tmp_path / "budget.sqlite3"
    db.reset(database_path, db.EVAL_SEED_NAME)
    caller = SequenceCaller(
        [ModelTurn(message={"role": "assistant", "content": "Stop."})]
    )
    budget = RunBudget(model_responses=MAX_MODEL_RESPONSES - 1)
    policy = candidate_policy_for_case("C10")
    with db.connect(database_path) as connection:
        context = ToolContext(
            connection, AgentState(), lambda: 1_800_000_000, policy=policy
        )
        first = run_tool_program(
            context,
            [{"role": "user", "content": "Compare."}],
            caller,
            candidate_program(policy),
            budget=budget,
        )
        second = run_tool_program(
            context,
            [{"role": "user", "content": "Continue."}],
            caller,
            candidate_program(policy),
            budget=budget,
        )

    assert first.status == "complete"
    assert second.reason == "model_response_limit"
    assert caller.calls == 1


def test_frozen_assignment_ledger_still_has_exact_paired_denominator() -> None:
    assignments = build_assignments()
    assert len(assignments) == 48
    for pair_id in {row["pair_id"] for row in assignments}:
        rows = [row for row in assignments if row["pair_id"] == pair_id]
        assert {row["condition"] for row in rows} == {"directbuy", "orderseal"}
        assert all(row["denominator_included"] for row in rows)


def test_preregistration_is_self_bound_and_withholds_scored_execution() -> None:
    from app.domain import digest

    manifest = build_preregistration(
        source_revision="1" * 40,
        frozen_by="test-owner",
        frozen_at="2026-08-30T00:00:00+00:00",
    )
    manifest_digest = manifest.pop("manifest_digest")

    assert manifest_digest == digest("orderseal-preregistration-v1", manifest)
    assert manifest["design"]["assignment_count"] == 48
    assert manifest["design"]["pair_count"] == 24
    assert manifest["provider_contract"]["requested_model"] == MODEL_ID
    assert manifest["provider_contract"]["upstream_provider_order"] == ["openai"]
    assert manifest["provider_contract"]["allow_fallbacks"] is False
    assert manifest["authorization_gate"]["scored_execution_authorized"] is False
    assert manifest["denominator_and_failure_rules"]["selective_retry"] is False


def test_runtime_provider_contract_cannot_drift_via_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "not-the-frozen-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://different.invalid/v9")

    settings = frozen_provider_settings()

    assert settings.model == MODEL_ID
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.provider_order == ("openai",)
    assert settings.allow_fallbacks is False
    assert settings.require_parameters is True
