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
    ModelTurn,
    OpenRouterCaller,
    ProviderError,
    investigate_exact_sku,
    tool_names,
)
from app.domain import canonical_json


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
    assert "confirm_order" not in canonical_json(TOOL_SCHEMAS)


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
