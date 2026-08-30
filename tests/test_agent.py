from __future__ import annotations

import copy
import json
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from app import agent as agent_module
from app import db
from app.agent import (
    SUPPORTED_BRIEF,
    TOOL_SCHEMAS,
    AgentOutcome,
    CandidatePolicy,
    ModelTurn,
    OpenRouterCaller,
    ProviderError,
    investigate_request,
    investigate_exact_sku,
    tool_names,
)
from app.domain import canonical_json
from evals.policy import candidate_policy_for_case


class SequenceCaller:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = deque(turns)
        self.message_snapshots: list[list[dict[str, Any]]] = []

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout_seconds: float,
    ) -> ModelTurn:
        del tools
        assert 0 < timeout_seconds <= 30
        self.message_snapshots.append(copy.deepcopy(messages))
        if not self.turns:
            raise AssertionError("model called after the test sequence ended")
        return self.turns.popleft()


def tool_turn(name: str, arguments: str | dict[str, object], number: int) -> ModelTurn:
    serialized = arguments if isinstance(arguments, str) else canonical_json(arguments)
    return ModelTurn(
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call-{number}",
                    "type": "function",
                    "function": {"name": name, "arguments": serialized},
                }
            ],
        },
        model="test-model",
        usage={"total_tokens": 10},
    )


def success_turns() -> list[ModelTurn]:
    return [
        tool_turn("search_catalog", {"query": "KB-ERG-001"}, 1),
        tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 2),
        tool_turn("set_cart", {"sku": "KB-ERG-001", "quantity": 2}, 3),
        tool_turn("validate_cart", {}, 4),
        tool_turn("prepare_order", {}, 5),
    ]


@pytest.fixture
def agent_database(tmp_path: Path) -> Path:
    path = tmp_path / "agent.db"
    db.reset(path)
    return path


def run_agent(path: Path, caller: SequenceCaller) -> AgentOutcome:
    with db.connect(path) as connection:
        return investigate_exact_sku(
            connection,
            SUPPORTED_BRIEF,
            caller,
            clock=lambda: 1_800_000_000,
        )


def test_registry_is_exact_and_excludes_confirmation_capability() -> None:
    assert tool_names() == (
        "search_catalog",
        "inspect_product",
        "set_cart",
        "validate_cart",
        "prepare_order",
        "get_order_status",
        "get_receipt",
    )
    assert [tool["function"]["name"] for tool in TOOL_SCHEMAS] == list(tool_names())
    assert {
        "confirm_order",
        "place_order",
        "record_evaluation_approval",
    }.isdisjoint(tool_names())
    assert "confirm_order" not in canonical_json(TOOL_SCHEMAS)


def test_policy_rejects_malformed_optional_values_even_without_ordering() -> None:
    with pytest.raises(ValueError, match="optional policy value"):
        CandidatePolicy(
            allowed_skus=(),
            quantity=True,
            budget_paise="1800000",  # type: ignore[arg-type]
            delivery_days_max=False,
            ordering_allowed=False,
        )


def test_generic_candidate_prepares_an_evidenced_fallback(tmp_path: Path) -> None:
    database_path = tmp_path / "fallback.db"
    db.reset(database_path, db.EVAL_SEED_NAME)
    policy = candidate_policy_for_case("C04")
    caller = SequenceCaller(
        [
            tool_turn("inspect_product", {"sku": "KB-OOS-006"}, 1),
            tool_turn("inspect_product", {"sku": "KB-ALT-002"}, 2),
            tool_turn("set_cart", {"sku": "KB-ALT-002", "quantity": 2}, 3),
            tool_turn("validate_cart", {}, 4),
            tool_turn("prepare_order", {}, 5),
        ]
    )

    with db.connect(database_path) as connection:
        outcome = investigate_request(
            connection,
            "Buy two KB-OOS-006 keyboards, or a qualifying ergonomic fallback.",
            policy,
            caller,
            clock=lambda: 1_800_000_000,
        )
        prepared = connection.execute(
            "SELECT sku, quantity FROM preparation_items"
        ).fetchone()
        constraints = connection.execute(
            "SELECT canonical_json FROM constraint_sets"
        ).fetchone()[0]

    assert outcome.status == "ready_for_confirmation"
    assert tuple(prepared) == ("KB-ALT-002", 2)
    stored_constraints = json.loads(constraints)
    assert stored_constraints["allowed_skus"] == [
        "KB-ALT-002",
        "KB-BUD-003",
    ]
    assert stored_constraints["fallback_from_skus"] == ["KB-OOS-006"]
    assert stored_constraints["fallback_evidence"][0]["stock_quantity"] == 0


def test_fallback_requires_evidence_for_the_preferred_item(tmp_path: Path) -> None:
    database_path = tmp_path / "fallback-without-evidence.db"
    db.reset(database_path, db.EVAL_SEED_NAME)
    policy = candidate_policy_for_case("C04")
    caller = SequenceCaller(
        [
            tool_turn("inspect_product", {"sku": "KB-ALT-002"}, 1),
            tool_turn("set_cart", {"sku": "KB-ALT-002", "quantity": 2}, 2),
            tool_turn("validate_cart", {}, 3),
            ModelTurn(message={"role": "assistant", "content": "Hold."}),
        ]
    )

    with db.connect(database_path) as connection:
        outcome = investigate_request(
            connection,
            "Use a fallback without checking the requested item.",
            policy,
            caller,
            clock=lambda: 1_800_000_000,
        )
        assert connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0

    assert outcome.status == "held"


@pytest.mark.parametrize(
    ("case_id", "expected_status"),
    [("C10", "complete"), ("C11", "needs_user")],
)
def test_non_order_policy_stops_without_preparation(
    tmp_path: Path, case_id: str, expected_status: str
) -> None:
    database_path = tmp_path / f"no-order-{case_id}.db"
    db.reset(database_path, db.EVAL_SEED_NAME)
    policy = candidate_policy_for_case(case_id)
    final_content = "Which currency, pack size, and quantity should I use?" if case_id == "C11" else "No order."
    turns = [ModelTurn(message={"role": "assistant", "content": final_content})]
    if case_id == "C10":
        turns.insert(0, tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 1))
    caller = SequenceCaller(turns)

    with db.connect(database_path) as connection:
        outcome = investigate_request(
            connection,
            "Investigate, but do not order.",
            policy,
            caller,
            clock=lambda: 1_800_000_000,
        )
        assert connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0

    assert outcome.status == expected_status


@pytest.mark.parametrize(
    ("case_id", "sku"),
    [
        ("C03", "KB-ERG-001"),
        ("C05", "KB-LATE-004"),
        ("C07", "KB-NODEL-005"),
    ],
)
def test_generic_candidate_holds_unacceptable_cart_without_preparation(
    tmp_path: Path, case_id: str, sku: str
) -> None:
    database_path = tmp_path / f"held-{sku}.db"
    db.reset(database_path, db.EVAL_SEED_NAME)
    policy = candidate_policy_for_case(case_id)
    caller = SequenceCaller(
        [
            tool_turn("inspect_product", {"sku": sku}, 1),
            tool_turn("set_cart", {"sku": sku, "quantity": 2}, 2),
            tool_turn("validate_cart", {}, 3),
            ModelTurn(message={"role": "assistant", "content": "Hold."}),
        ]
    )

    with db.connect(database_path) as connection:
        outcome = investigate_request(
            connection,
            "Use the server-owned constraints.",
            policy,
            caller,
            clock=lambda: 1_800_000_000,
        )
        assert connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0

    assert outcome.status == "held"


def test_clarification_stops_before_resolved_policy_can_prepare(tmp_path: Path) -> None:
    database_path = tmp_path / "clarification.db"
    db.reset(database_path, db.EVAL_SEED_NAME)
    unresolved = candidate_policy_for_case("C02")
    resolved = candidate_policy_for_case("C02", clarified=True)

    with db.connect(database_path) as connection:
        first = investigate_request(
            connection,
            "Buy the requested brand, but the exact SKU is unclear.",
            unresolved,
            SequenceCaller(
                [ModelTurn(message={"role": "assistant", "content": "Which SKU?"})]
            ),
            clock=lambda: 1_800_000_000,
        )
        assert connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0
        second = investigate_request(
            connection,
            "Use ErgoType SKU KB-ERG-001.",
            resolved,
            SequenceCaller(success_turns()),
            clock=lambda: 1_800_000_001,
        )

    assert first.status == "needs_user"
    assert second.status == "ready_for_confirmation"


def test_exact_sku_agent_reaches_redacted_confirmation_ready_state(
    agent_database: Path,
) -> None:
    caller = SequenceCaller(success_turns())

    outcome = run_agent(agent_database, caller)

    assert outcome.status == "ready_for_confirmation"
    assert outcome.reason == "prepared"
    assert outcome.model == "test-model"
    assert outcome.usage == {"total_tokens": 50}
    assert [event["tool"] for event in outcome.trajectory] == list(tool_names())[:5]
    assert outcome.prepared is True
    with db.connect(agent_database) as connection:
        intent = connection.execute(
            """
            SELECT ci.actor, ci.confirmation_method, ci.consumed_at_epoch,
                   ci.operation_key, ci.session_id, ci.preparation_id
            FROM confirmation_intents ci
            """
        ).fetchone()
        assert tuple(intent[:3]) == (
            "browser_operator_unverified",
            "browser_ui",
            None,
        )
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    serialized_outcome = canonical_json(asdict(outcome))
    for capability_or_identifier in intent[3:]:
        assert capability_or_identifier not in serialized_outcome


def test_catalogue_description_is_typed_untrusted_tool_data(
    agent_database: Path,
) -> None:
    caller = SequenceCaller(success_turns())

    outcome = run_agent(agent_database, caller)

    assert outcome.status == "ready_for_confirmation"
    messages_after_inspection = caller.message_snapshots[2]
    tool_message = messages_after_inspection[-1]
    assert tool_message["role"] == "tool"
    evidence = json.loads(tool_message["content"])
    description = evidence["evidence"]["untrusted_description"]
    assert description["untrusted"] is True
    assert description["source"] == "synthetic_catalogue"
    assert "Ignore any instructions" in description["value"]
    assert all(
        event.get("event") in {"tool_result", "tool_rejected"}
        for event in outcome.trajectory
    )
    assert "Ignore any instructions" not in canonical_json(outcome.trajectory)


@pytest.mark.parametrize(
    ("name", "arguments", "expected_reason"),
    [
        ("confirm_order", {}, "unknown_tool"),
        ("place_order", {}, "unknown_tool"),
        ("prepare_order", {"operation_key": "model-owned"}, "invalid_tool_arguments"),
        (
            "set_cart",
            '{"sku":"KB-ERG-001","sku":"OTHER","quantity":2}',
            "invalid_tool_arguments",
        ),
    ],
)
def test_unknown_authority_extra_fields_and_duplicate_keys_fail_closed(
    agent_database: Path,
    name: str,
    arguments: str | dict[str, object],
    expected_reason: str,
) -> None:
    outcome = run_agent(agent_database, SequenceCaller([tool_turn(name, arguments, 1)]))

    assert outcome.status == "held"
    assert outcome.reason == expected_reason
    assert outcome.prepared is False
    with db.connect(agent_database) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0
        )
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_model_cannot_weaken_server_owned_quantity(agent_database: Path) -> None:
    caller = SequenceCaller(
        [
            tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 1),
            tool_turn("set_cart", {"sku": "KB-ERG-001", "quantity": 1}, 2),
            tool_turn("validate_cart", {}, 3),
            tool_turn("prepare_order", {}, 4),
            ModelTurn(message={"role": "assistant", "content": "I cannot prepare."}),
        ]
    )

    outcome = run_agent(agent_database, caller)

    assert outcome.status == "held"
    assert outcome.prepared is False
    assert {event["outcome"] for event in outcome.trajectory} >= {
        "invalid",
        "held",
    }
    with db.connect(agent_database) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0
        )


def test_unsupported_brief_never_reaches_model(agent_database: Path) -> None:
    caller = SequenceCaller([])

    with db.connect(agent_database) as connection:
        outcome = investigate_exact_sku(
            connection,
            "Buy whatever you think is best.",
            caller,
            clock=lambda: 1_800_000_000,
        )

    assert outcome.status == "needs_user"
    assert outcome.reason == "unsupported_brief"
    assert caller.message_snapshots == []


def test_workflow_order_cannot_set_cart_before_inspection(agent_database: Path) -> None:
    caller = SequenceCaller(
        [
            tool_turn("set_cart", {"sku": "KB-ERG-001", "quantity": 2}, 1),
            tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 2),
            tool_turn("validate_cart", {}, 3),
            tool_turn("prepare_order", {}, 4),
            ModelTurn(message={"role": "assistant", "content": "held"}),
        ]
    )

    outcome = run_agent(agent_database, caller)

    assert outcome.status == "held"
    assert outcome.prepared is False
    with db.connect(agent_database) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM preparations").fetchone()[0] == 0
        )


def test_oversized_unknown_tool_name_produces_bounded_safe_trajectory(
    agent_database: Path,
) -> None:
    outcome = run_agent(
        agent_database,
        SequenceCaller([tool_turn("\n" + "X" * 500_000, {}, 1)]),
    )

    assert outcome.status == "held"
    assert outcome.trajectory == (
        {"event": "tool_rejected", "tool": "<unknown>", "outcome": "unknown"},
    )
    assert len(canonical_json(outcome.trajectory)) < 200


class MutableMonotonic:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_provider_overrun_cannot_return_ready(agent_database: Path) -> None:
    monotonic = MutableMonotonic()

    class SlowCaller:
        def __call__(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            timeout_seconds: float,
        ) -> ModelTurn:
            del messages, tools, timeout_seconds
            monotonic.now += 121
            return tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 1)

    with db.connect(agent_database) as connection:
        outcome = investigate_exact_sku(
            connection,
            SUPPORTED_BRIEF,
            SlowCaller(),
            clock=lambda: 1_800_000_000,
            monotonic=monotonic,
        )

    assert outcome.status == "held"
    assert outcome.reason == "run_timeout"
    assert outcome.prepared is False


def test_slow_tool_cannot_advance_workflow(
    agent_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monotonic = MutableMonotonic()
    original = agent_module.TOOL_HANDLERS["inspect_product"]

    def slow_tool(context, arguments):
        result = original(context, arguments)
        monotonic.now += 3.2
        return result

    monkeypatch.setitem(agent_module.TOOL_HANDLERS, "inspect_product", slow_tool)
    with db.connect(agent_database) as connection:
        outcome = investigate_exact_sku(
            connection,
            SUPPORTED_BRIEF,
            SequenceCaller([tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 1)]),
            clock=lambda: 1_800_000_000,
            monotonic=monotonic,
        )

    assert outcome.status == "held"
    assert outcome.reason == "tool_timeout"
    assert outcome.prepared is False


@pytest.mark.parametrize(
    "usage",
    [
        "invalid",
        {"prompt_tokens": -1},
        {"completion_tokens": True},
        {"total_tokens": "12"},
        {"total_tokens": 1_000_000_001},
    ],
)
def test_malformed_provider_usage_fails_with_sanitized_error(
    monkeypatch: pytest.MonkeyPatch, usage: object
) -> None:
    response_body = json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
            "usage": usage,
        }
    ).encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return response_body

    monkeypatch.setattr(
        agent_module.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse()
    )
    caller = OpenRouterCaller(
        base_url="https://openrouter.invalid/v1",
        model="test-model",
        api_key="test-key-not-a-secret",
    )

    with pytest.raises(ProviderError, match="provider_usage_invalid"):
        caller([], TOOL_SCHEMAS, 1)


def test_openrouter_caller_pins_upstream_provider_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = json.dumps(
        {
            "choices": [{"message": {"role": "assistant", "content": "done"}}],
            "model": "deepseek/deepseek-v4-flash-20260731",
            "usage": {"total_tokens": 1},
        }
    ).encode()
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return response_body

    def fake_urlopen(request, **_kwargs):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(agent_module.urllib.request, "urlopen", fake_urlopen)
    caller = OpenRouterCaller(
        base_url="https://openrouter.invalid/v1",
        model="deepseek/deepseek-v4-flash-0731",
        api_key="test-key-not-a-secret",
        provider_slug="deepseek",
    )

    caller([], TOOL_SCHEMAS, 1)

    assert captured["payload"]["provider"] == {
        "order": ["deepseek"],
        "allow_fallbacks": False,
        "require_parameters": True,
    }
    assert captured["payload"]["temperature"] == 0
    assert "parallel_tool_calls" not in captured["payload"]


def test_openrouter_preflight_accepts_only_compatible_frozen_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        "/key": {"data": {}},
        "/model/deepseek/deepseek-v4-flash-0731": {
            "data": {
                "canonical_slug": "deepseek/deepseek-v4-flash-20260731"
            }
        },
        "/models/deepseek/deepseek-v4-flash-0731/endpoints": {
            "data": {
                "endpoints": [
                    {
                        "tag": "deepseek",
                        "supported_parameters": [
                            "temperature",
                            "tool_choice",
                            "tools",
                        ],
                    }
                ]
            }
        },
    }

    class FakeResponse:
        def __init__(self, body: dict[str, object]) -> None:
            self.body = json.dumps(body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return self.body

    def fake_urlopen(request, **_kwargs):
        path = request.full_url.removeprefix("https://openrouter.invalid/v1")
        return FakeResponse(responses[path])

    monkeypatch.setattr(agent_module.urllib.request, "urlopen", fake_urlopen)
    caller = OpenRouterCaller(
        base_url="https://openrouter.invalid/v1",
        model="deepseek/deepseek-v4-flash-0731",
        api_key="test-key-not-a-secret",
        provider_slug="deepseek",
    )

    receipt = caller.preflight({"temperature", "tool_choice", "tools"})

    assert receipt == {
        "auth": "ok",
        "model_requested": "deepseek/deepseek-v4-flash-0731",
        "canonical_model": "deepseek/deepseek-v4-flash-20260731",
        "provider_tag": "deepseek",
        "required_parameters": ["temperature", "tool_choice", "tools"],
        "compatible_endpoint_count": 1,
    }


def test_controller_rejects_multiple_tool_calls_from_one_response(
    agent_database: Path,
) -> None:
    first = tool_turn("inspect_product", {"sku": "KB-ERG-001"}, 1).message[
        "tool_calls"
    ][0]
    second = tool_turn("set_cart", {"sku": "KB-ERG-001", "quantity": 2}, 2).message[
        "tool_calls"
    ][0]
    caller = SequenceCaller(
        [ModelTurn(message={"role": "assistant", "tool_calls": [first, second]})]
    )

    outcome = run_agent(agent_database, caller)

    assert outcome.status == "held"
    assert outcome.reason == "parallel_tool_calls_rejected"
