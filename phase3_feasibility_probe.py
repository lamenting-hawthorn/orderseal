from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app import db
from app.agent import (
    CANDIDATE_PROGRAM,
    SUPPORTED_BRIEF,
    SYSTEM_PROMPT,
    AgentState,
    OpenRouterCaller,
    ToolContext,
    run_tool_program,
)
from app.baseline import run_direct_buy
from app.domain import (
    canonical_json,
    confirm_order,
    reconcile_order,
    record_acknowledgement_loss,
    record_evaluation_approval,
    record_evaluation_fault_delivery,
)
from gate_zero import load_settings

ROOT = Path(__file__).resolve().parent
RECEIPT_FILE = ROOT / "PHASE3_FEASIBILITY_RECEIPT.json"
RUN_ID = "phase3-unscored-feasibility"


def _hashes() -> dict[str, str]:
    paths = (
        "app/agent.py",
        "app/baseline.py",
        "app/db.py",
        "app/domain.py",
        "phase3_feasibility_probe.py",
    )
    return {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }


def _approval_provider(connection: Any, now_epoch: int):
    def approve(session_id: str, snapshot: dict[str, Any]) -> str:
        return record_evaluation_approval(
            connection,
            run_id=f"{RUN_ID}-directbuy",
            condition="directbuy",
            session_id=session_id,
            displayed_cart_digest=snapshot["displayed_cart_digest"],
            decision="approved",
            actor="scripted_evaluator",
            displayed_at_monotonic_ms=1_000,
            decided_at_monotonic_ms=1_200,
            server_received_at_epoch=now_epoch,
        )

    return approve


def _candidate_probe(caller: OpenRouterCaller, now_epoch: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="orderseal-phase3-candidate-") as directory:
        database_path = Path(directory) / "candidate.db"
        db.reset(database_path)
        with db.connect(database_path) as connection:
            state = AgentState()
            context = ToolContext(
                connection,
                state,
                lambda: now_epoch,
                preparation_actor="scripted_evaluator",
                confirmation_method="evaluation_api",
                fault_kind="post_commit_ack_loss",
            )
            outcome = run_tool_program(
                context,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": SUPPORTED_BRIEF},
                ],
                caller,
                CANDIDATE_PROGRAM,
            )
            prepared = state.prepared
            reconciled = False
            order_count = 0
            if outcome.status == "ready_for_confirmation" and prepared is not None:
                cart_digest = connection.execute(
                    "SELECT cart_digest FROM preparations WHERE id = ?",
                    (prepared.preparation_id,),
                ).fetchone()["cart_digest"]
                record_evaluation_approval(
                    connection,
                    run_id=f"{RUN_ID}-orderseal",
                    condition="orderseal",
                    session_id=prepared.session_id,
                    displayed_cart_digest=cart_digest,
                    decision="approved",
                    actor="scripted_evaluator",
                    displayed_at_monotonic_ms=1_000,
                    decided_at_monotonic_ms=1_200,
                    server_received_at_epoch=now_epoch,
                )
                result = confirm_order(
                    connection,
                    session_id=prepared.session_id,
                    preparation_id=prepared.preparation_id,
                    preparation_digest=prepared.preparation_digest,
                    intent_nonce=prepared.intent_nonce,
                    operation_key=prepared.operation_key,
                    clock=lambda: now_epoch,
                )
                record_acknowledgement_loss(
                    connection, result.receipt["order_id"], now_epoch
                )
                record_evaluation_fault_delivery(
                    connection,
                    run_id=f"{RUN_ID}-orderseal",
                    condition="orderseal",
                    order_id=result.receipt["order_id"],
                    commit_observed_monotonic_ms=2_000,
                    injector_triggered_monotonic_ms=2_001,
                    acknowledgement_suppressed_monotonic_ms=2_002,
                    response_returned_monotonic_ms=2_003,
                )
                reconcile_order(
                    connection,
                    session_id=prepared.session_id,
                    preparation_id=prepared.preparation_id,
                    preparation_digest=prepared.preparation_digest,
                    operation_key=prepared.operation_key,
                )
                reconciled = True
                order_count = connection.execute(
                    "SELECT COUNT(*) FROM orders"
                ).fetchone()[0]
            external_fault_count = connection.execute(
                "SELECT COUNT(*) FROM evaluation_fault_events"
            ).fetchone()[0]
            durable_fault_count = connection.execute(
                "SELECT COUNT(*) FROM fault_events"
            ).fetchone()[0]
            fault_proof = external_fault_count == durable_fault_count == 1
    return {
        "ok": outcome.status == "ready_for_confirmation"
        and reconciled
        and order_count == 1
        and fault_proof,
        "status": outcome.status,
        "reason": outcome.reason,
        "tools": [event["tool"] for event in outcome.trajectory],
        "usage": outcome.usage,
        "order_count": order_count,
        "reconciled": reconciled,
        "fault_proof": fault_proof,
    }


def _directbuy_probe(caller: OpenRouterCaller, now_epoch: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="orderseal-phase3-directbuy-") as directory:
        database_path = Path(directory) / "directbuy.db"
        db.reset(database_path)
        with db.connect(database_path) as connection:
            run = run_direct_buy(
                connection,
                SUPPORTED_BRIEF,
                caller,
                run_id=f"{RUN_ID}-directbuy",
                approval_provider=_approval_provider(connection, now_epoch),
                clock=lambda: now_epoch,
                evaluation_mode=True,
                fault_kind="post_commit_ack_loss",
            )
            order_count = connection.execute(
                "SELECT COUNT(*) FROM directbuy_orders"
            ).fetchone()[0]
            order = connection.execute(
                "SELECT id FROM directbuy_orders"
            ).fetchone()
            if run.outcome.status == "complete" and order is not None:
                record_evaluation_fault_delivery(
                    connection,
                    run_id=f"{RUN_ID}-directbuy",
                    condition="directbuy",
                    order_id=order["id"],
                    commit_observed_monotonic_ms=2_000,
                    injector_triggered_monotonic_ms=2_001,
                    acknowledgement_suppressed_monotonic_ms=2_002,
                    response_returned_monotonic_ms=2_003,
                )
            external_fault_count = connection.execute(
                "SELECT COUNT(*) FROM evaluation_fault_events"
            ).fetchone()[0]
            durable_fault_count = connection.execute(
                "SELECT COUNT(*) FROM directbuy_fault_events"
            ).fetchone()[0]
            fault_proof = external_fault_count == durable_fault_count == 1
    return {
        "ok": run.outcome.status == "complete"
        and order_count == 1
        and fault_proof,
        "status": run.outcome.status,
        "reason": run.outcome.reason,
        "tools": [event["tool"] for event in run.outcome.trajectory],
        "usage": run.outcome.usage,
        "order_count": order_count,
        "reconciled": run.outcome.reason == "placed_and_reconciled",
        "fault_proof": fault_proof,
    }


def main() -> int:
    settings = load_settings()
    caller = OpenRouterCaller(
        base_url=settings["ORDERSEAL_BASE_URL"],
        model=settings["ORDERSEAL_MODEL"],
        api_key=settings["ORDERSEAL_API_KEY"],
    )
    now_epoch = int(time.time())
    candidate = _candidate_probe(caller, now_epoch)
    directbuy = _directbuy_probe(caller, now_epoch)
    receipt = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "source_revision": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "dirty_candidate": True,
        "candidate_sha256": _hashes(),
        "provider_base_url": settings["ORDERSEAL_BASE_URL"].rstrip("/"),
        "model_requested": settings["ORDERSEAL_MODEL"],
        "fault_profile": "post_commit_ack_loss",
        "proof_layer": "unscored_live_provider_local_sqlite",
        "candidate": candidate,
        "directbuy": directbuy,
        "ok": bool(candidate["ok"] and directbuy["ok"]),
    }
    RECEIPT_FILE.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(
        canonical_json(
            {
                "ok": receipt["ok"],
                "candidate": candidate["status"],
                "directbuy": directbuy["status"],
            }
        )
    )
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
