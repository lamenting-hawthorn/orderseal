from __future__ import annotations

import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from app import db
from app.agent import SUPPORTED_BRIEF, ModelTurn
from app.baseline import (
    DIRECTBUY_TOOL_SCHEMAS,
    directbuy_tool_names,
    place_direct_order,
    run_direct_buy,
)
from app.domain import (
    DomainError,
    confirm_order,
    create_evaluation_session,
    displayed_cart,
    prepare_demo,
    record_acknowledgement_loss,
    record_evaluation_approval,
    record_evaluation_fault_delivery,
)
from evals.protocol import CASE_IDS, build_assignments, load_cases, load_expectations
from evals.run import run_simulation
from evals.score import open_query_only, score_database


class SequenceCaller:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = deque(turns)

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout_seconds: float,
    ) -> ModelTurn:
        del messages, tools, timeout_seconds
        return self.turns.popleft()


def tool_turn(name: str, arguments: str, number: int) -> ModelTurn:
    return ModelTurn(
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"direct-call-{number}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        },
        model="test-model",
        usage={"total_tokens": 5},
    )


def direct_turns(*, reconcile: bool = False) -> list[ModelTurn]:
    turns = [
        tool_turn("inspect_product", '{"sku":"KB-ERG-001"}', 1),
        tool_turn(
            "set_cart", '{"sku":"KB-ERG-001","quantity":2}', 2
        ),
        tool_turn("place_order", "{}", 3),
    ]
    if reconcile:
        turns.append(tool_turn("get_order_history", "{}", 4))
    return turns


def approve(
    connection: sqlite3.Connection, run_id: str
):
    def provider(session_id: str, snapshot: dict[str, Any]) -> str:
        return record_evaluation_approval(
            connection,
            run_id=run_id,
            condition="directbuy",
            session_id=session_id,
            displayed_cart_digest=snapshot["displayed_cart_digest"],
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=100,
            decided_at_monotonic_ms=200,
            server_received_at_epoch=1_800_000_000,
        )

    return provider


def assignment(run_id: str, condition: str) -> dict[str, str]:
    return {"run_id": run_id, "condition": condition}


def test_baseline_registry_is_separate_and_has_no_authority_arguments() -> None:
    assert directbuy_tool_names() == (
        "search_catalog",
        "inspect_product",
        "set_cart",
        "place_order",
        "get_order_history",
    )
    assert [schema["function"]["name"] for schema in DIRECTBUY_TOOL_SCHEMAS] == list(
        directbuy_tool_names()
    )
    place_schema = DIRECTBUY_TOOL_SCHEMAS[3]["function"]["parameters"]
    assert place_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_directbuy_places_one_approved_order_without_candidate_capability(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "direct.db"
    db.reset(database_path)
    with db.connect(database_path) as connection:
        run = run_direct_buy(
            connection,
            SUPPORTED_BRIEF,
            SequenceCaller(direct_turns()),
            run_id="feasible-directbuy",
            approval_provider=approve(connection, "feasible-directbuy"),
            clock=lambda: 1_800_000_000,
        )

        assert run.outcome.status == "complete"
        assert run.outcome.reason == "placed"
        assert run.outcome.prepared is False
        assert connection.execute("SELECT COUNT(*) FROM directbuy_orders").fetchone()[
            0
        ] == 1
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert connection.execute(
            "SELECT actor FROM evaluation_approval_events"
        ).fetchone()[0] == "scripted_evaluator"


def test_directbuy_ack_loss_requires_history_and_does_not_duplicate(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ack.db"
    db.reset(database_path)
    with db.connect(database_path) as connection:
        run = run_direct_buy(
            connection,
            SUPPORTED_BRIEF,
            SequenceCaller(direct_turns(reconcile=True)),
            run_id="feasible-directbuy-ack",
            approval_provider=approve(connection, "feasible-directbuy-ack"),
            clock=lambda: 1_800_000_000,
            evaluation_mode=True,
            fault_kind="post_commit_ack_loss",
        )

        assert run.outcome.status == "complete"
        assert run.outcome.reason == "placed_and_reconciled"
        assert [event["outcome"] for event in run.outcome.trajectory][-2:] == [
            "ack_unknown",
            "complete",
        ]
        assert connection.execute("SELECT COUNT(*) FROM directbuy_orders").fetchone()[
            0
        ] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM directbuy_fault_events"
        ).fetchone()[0] == 1


def test_directbuy_fault_is_refused_without_evaluation_mode(tmp_path: Path) -> None:
    database_path = tmp_path / "no-fault.db"
    db.reset(database_path)
    with db.connect(database_path) as connection:
        with pytest.raises(ValueError, match="requires evaluation mode"):
            run_direct_buy(
                connection,
                SUPPORTED_BRIEF,
                SequenceCaller([]),
                run_id="fault-refused",
                approval_provider=approve(connection, "fault-refused"),
                clock=lambda: 1_800_000_000,
                fault_kind="post_commit_ack_loss",
            )
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_direct_order_rejects_stale_or_cross_session_approval(tmp_path: Path) -> None:
    database_path = tmp_path / "approval.db"
    db.reset(database_path)
    with db.connect(database_path) as connection:
        session_id = create_evaluation_session(connection, 1_800_000_000)
        other_session = create_evaluation_session(connection, 1_800_000_000)
        snapshot = displayed_cart(connection, sku="KB-ERG-001", quantity=2)
        approval_id = record_evaluation_approval(
            connection,
            run_id="approval-boundary",
            condition="directbuy",
            session_id=session_id,
            displayed_cart_digest=snapshot["displayed_cart_digest"],
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_000,
        )
        with pytest.raises(DomainError, match="approval_invalid"):
            place_direct_order(
                connection,
                run_id="approval-boundary",
                session_id=other_session,
                sku="KB-ERG-001",
                quantity=2,
                approval_event_id=approval_id,
                clock=lambda: 1_800_000_000,
            )
        connection.execute(
            "UPDATE products SET unit_price_paise = unit_price_paise + 1, version = version + 1"
        )
        with pytest.raises(DomainError, match="approval_invalid"):
            place_direct_order(
                connection,
                run_id="approval-boundary",
                session_id=session_id,
                sku="KB-ERG-001",
                quantity=2,
                approval_event_id=approval_id,
                clock=lambda: 1_800_000_000,
            )
        assert connection.execute("SELECT COUNT(*) FROM directbuy_orders").fetchone()[
            0
        ] == 0


def test_frozen_case_and_ab_ba_assignment_contract() -> None:
    assert tuple(case["case_id"] for case in load_cases()) == CASE_IDS
    assert tuple(load_expectations()) == CASE_IDS
    assignments = build_assignments()
    assert len(assignments) == 48
    assert len({row["run_id"] for row in assignments}) == 48
    assert all(row["denominator_included"] for row in assignments)
    for case_id in CASE_IDS:
        repeat_one = sorted(
            (row for row in assignments if row["pair_id"] == f"{case_id}-R1"),
            key=lambda row: row["within_block_order"],
        )
        repeat_two = sorted(
            (row for row in assignments if row["pair_id"] == f"{case_id}-R2"),
            key=lambda row: row["within_block_order"],
        )
        assert [row["condition"] for row in repeat_one] == [
            row["condition"] for row in reversed(repeat_two)
        ]


def test_query_only_oracle_scores_one_valid_order_and_detects_duplicate(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "oracle.db"
    db.reset(database_path)
    expectation = load_expectations()["C01"]
    with db.connect(database_path) as connection:
        session_id = create_evaluation_session(connection, 1_800_000_000)
        snapshot = displayed_cart(connection, sku="KB-ERG-001", quantity=2)
        approval_id = record_evaluation_approval(
            connection,
            run_id="oracle-run",
            condition="directbuy",
            session_id=session_id,
            displayed_cart_digest=snapshot["displayed_cart_digest"],
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_000,
        )
        place_direct_order(
            connection,
            run_id="oracle-run",
            session_id=session_id,
            sku="KB-ERG-001",
            quantity=2,
            approval_event_id=approval_id,
            clock=lambda: 1_800_000_000,
        )

    claim = {
        "terminal_state": "complete",
        "effect_claim": "committed",
        "reconciled": False,
    }
    scored = score_database(
        database_path, assignment("oracle-run", "directbuy"), expectation, claim
    )
    assert scored["metrics"]["safe_task_outcome"] is True
    with open_query_only(database_path) as query_only:
        with pytest.raises(sqlite3.OperationalError):
            query_only.execute("DELETE FROM directbuy_orders")

    with db.connect(database_path) as connection:
        place_direct_order(
            connection,
            run_id="oracle-run",
            session_id=session_id,
            sku="KB-ERG-001",
            quantity=2,
            approval_event_id=approval_id,
            clock=lambda: 1_800_000_000,
        )
    duplicate = score_database(
        database_path, assignment("oracle-run", "directbuy"), expectation, claim
    )
    assert duplicate["raw_observations"]["durable_order_count"] == 2
    assert duplicate["metrics"]["duplicate_order"] is True
    assert duplicate["metrics"]["safe_task_outcome"] is False


def test_oracle_requires_external_approval_for_candidate_effect(tmp_path: Path) -> None:
    database_path = tmp_path / "candidate-oracle.db"
    db.reset(database_path)
    claim = {
        "terminal_state": "complete",
        "effect_claim": "committed",
        "reconciled": False,
    }
    with db.connect(database_path) as connection:
        prepared = prepare_demo(
            connection,
            1_800_000_000,
            actor="scripted_evaluator",
            confirmation_method="evaluation_api",
        )
        confirm_order(
            connection,
            session_id=prepared.session_id,
            preparation_id=prepared.preparation_id,
            preparation_digest=prepared.preparation_digest,
            intent_nonce=prepared.intent_nonce,
            operation_key=prepared.operation_key,
            clock=lambda: 1_800_000_000,
        )
        cart_digest = connection.execute(
            "SELECT cart_digest FROM preparations WHERE id = ?",
            (prepared.preparation_id,),
        ).fetchone()["cart_digest"]

    with db.connect(database_path) as connection:
        record_evaluation_approval(
            connection,
            run_id="wrong-run",
            condition="directbuy",
            session_id=prepared.session_id,
            displayed_cart_digest=cart_digest,
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_000,
        )
    unapproved = score_database(
        database_path,
        assignment("candidate-oracle", "orderseal"),
        load_expectations()["C01"],
        claim,
    )
    assert unapproved["metrics"]["unauthorized_order"] is True
    assert unapproved["metrics"]["safe_task_outcome"] is False
    wrong_condition = score_database(
        database_path,
        assignment("wrong-run", "directbuy"),
        load_expectations()["C01"],
        claim,
    )
    assert wrong_condition["metrics"]["safe_task_outcome"] is False

    with db.connect(database_path) as connection:
        record_evaluation_approval(
            connection,
            run_id="candidate-posthoc",
            condition="orderseal",
            session_id=prepared.session_id,
            displayed_cart_digest=cart_digest,
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_100,
        )
    posthoc = score_database(
        database_path,
        assignment("candidate-posthoc", "orderseal"),
        load_expectations()["C01"],
        claim,
    )
    assert posthoc["raw_observations"]["approval_valid"] is False
    assert posthoc["metrics"]["safe_task_outcome"] is False

    with db.connect(database_path) as connection:
        record_evaluation_approval(
            connection,
            run_id="candidate-oracle",
            condition="orderseal",
            session_id=prepared.session_id,
            displayed_cart_digest=cart_digest,
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_000,
        )
    approved = score_database(
        database_path,
        assignment("candidate-oracle", "orderseal"),
        load_expectations()["C01"],
        claim,
    )
    assert approved["metrics"]["safe_task_outcome"] is True

    with db.connect(database_path) as connection:
        record_evaluation_approval(
            connection,
            run_id="candidate-oracle",
            condition="orderseal",
            session_id=prepared.session_id,
            displayed_cart_digest=cart_digest,
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_000,
        )
    ambiguous = score_database(
        database_path,
        assignment("candidate-oracle", "orderseal"),
        load_expectations()["C01"],
        claim,
    )
    assert ambiguous["raw_observations"]["approval_valid"] is False
    assert ambiguous["metrics"]["safe_task_outcome"] is False


def test_oracle_requires_ordered_run_bound_fault_delivery(tmp_path: Path) -> None:
    database_path = tmp_path / "fault-oracle.db"
    db.reset(database_path)
    run_id = "fault-oracle"
    with db.connect(database_path) as connection:
        prepared = prepare_demo(
            connection,
            1_800_000_000,
            actor="scripted_evaluator",
            confirmation_method="evaluation_api",
        )
        cart_digest = connection.execute(
            "SELECT cart_digest FROM preparations WHERE id = ?",
            (prepared.preparation_id,),
        ).fetchone()["cart_digest"]
        record_evaluation_approval(
            connection,
            run_id=run_id,
            condition="orderseal",
            session_id=prepared.session_id,
            displayed_cart_digest=cart_digest,
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1,
            decided_at_monotonic_ms=2,
            server_received_at_epoch=1_800_000_000,
        )
        result = confirm_order(
            connection,
            session_id=prepared.session_id,
            preparation_id=prepared.preparation_id,
            preparation_digest=prepared.preparation_digest,
            intent_nonce=prepared.intent_nonce,
            operation_key=prepared.operation_key,
            clock=lambda: 1_800_000_000,
        )
        order_id = result.receipt["order_id"]
        record_acknowledgement_loss(connection, order_id, 1_800_000_000)

    claim = {
        "terminal_state": "complete",
        "effect_claim": "committed",
        "reconciled": True,
    }
    relabelled_normal_ack = score_database(
        database_path,
        assignment(run_id, "orderseal"),
        load_expectations()["C08"],
        claim,
    )
    assert relabelled_normal_ack["raw_observations"][
        "fault_delivered_after_commit"
    ] is False
    assert relabelled_normal_ack["metrics"]["safe_task_outcome"] is False

    with db.connect(database_path) as connection:
        record_evaluation_fault_delivery(
            connection,
            run_id=run_id,
            condition="orderseal",
            order_id=order_id,
            commit_observed_monotonic_ms=10,
            injector_triggered_monotonic_ms=11,
            acknowledgement_suppressed_monotonic_ms=12,
            response_returned_monotonic_ms=13,
        )
    proven = score_database(
        database_path,
        assignment(run_id, "orderseal"),
        load_expectations()["C08"],
        claim,
    )
    assert proven["metrics"]["safe_task_outcome"] is True


def test_full_simulated_harness_preserves_all_frozen_denominators(
    tmp_path: Path,
) -> None:
    output = tmp_path / "simulation"

    summary = run_simulation(output)

    assert summary["assignment_count"] == 48
    assert summary["conditions"]["directbuy"]["safe_task_denominator"] == 24
    assert summary["conditions"]["orderseal"]["safe_task_denominator"] == 24
    assert len(list(output.glob("run-*/oracle.json"))) == 48
    assert len(list(output.glob("run-*/receipt.json"))) == 48
