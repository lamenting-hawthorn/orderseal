from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app import domain as domain_module
from app import main as main_module
from app.domain import DomainError, confirm_order, digest, preparation_payload
from app.main import ACK_UNKNOWN_MESSAGE, create_app


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000

    def __call__(self) -> int:
        return self.now


class HiddenInputs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attributes)
        if tag == "input" and values.get("type") == "hidden":
            name = values.get("name")
            value = values.get("value")
            if name is not None and value is not None:
                self.values[name] = value


@pytest.fixture
def orderseal(tmp_path: Path) -> tuple[TestClient, Path, Clock, FastAPI]:
    database_path = tmp_path / "orderseal-test.db"
    clock = Clock()
    application = create_app(
        database_path,
        clock=clock,
        eval_mode=True,
        allowed_origins={"https://testserver"},
        secure_cookies=True,
    )
    client = TestClient(application, base_url="https://testserver")
    return client, database_path, clock, application


def test_health(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path / "health.db")).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def start_evaluation(
    client: TestClient, *, fault: bool = False
) -> tuple[dict[str, object], dict[str, str]]:
    body = {"fault_kind": "post_commit_ack_loss"} if fault else {}
    response = client.post("/api/evaluation/start", json=body)
    assert response.status_code == 200
    payload = response.json()
    return payload["review"], payload["confirmation"]


def confirmation_payload(
    review: dict[str, object], confirmation: dict[str, str]
) -> dict[str, str]:
    return {
        "preparation_id": str(review["preparation_id"]),
        "preparation_digest": str(review["preparation_digest"]),
        "intent_nonce": confirmation["intent_nonce"],
        "operation_key": confirmation["operation_key"],
    }


def confirmation_headers(confirmation: dict[str, str]) -> dict[str, str]:
    return {
        "Origin": "https://testserver",
        "X-CSRF-Token": confirmation["csrf_token"],
    }


def confirm_evaluation(
    client: TestClient,
    review: dict[str, object],
    confirmation: dict[str, str],
):
    return client.post(
        "/api/evaluation/confirm",
        json=confirmation_payload(review, confirmation),
        headers=confirmation_headers(confirmation),
    )


def test_browser_confirmation_is_functional_and_truthfully_provenanced(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal

    review_page = client.post(
        "/demo/start", data={"brief": "Buy two keyboards <script>unsafe()</script>"}
    )
    assert review_page.status_code == 200
    assert "KB-ERG-001" in review_page.text
    assert "Total INR 15,000.00" in review_page.text
    assert 'action="/confirm-browser"' in review_page.text
    assert "Confirm exact synthetic order" in review_page.text
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in review_page.text
    assert "<script>unsafe()</script>" not in review_page.text
    set_cookie = review_page.headers["set-cookie"].lower()
    assert "secure" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    parser = HiddenInputs()
    parser.feed(review_page.text)
    confirmed = client.post(
        "/confirm-browser",
        data=parser.values,
        headers={"Origin": "https://testserver"},
    )

    assert confirmed.status_code == 200
    assert "Verified synthetic order" in confirmed.text
    assert "Authoritative SQLite" in confirmed.text
    with db.connect(database_path) as connection:
        event = connection.execute(
            "SELECT actor, confirmation_method FROM confirmation_events"
        ).fetchone()
        assert tuple(event) == ("browser_operator_unverified", "browser_ui")
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_documented_http_local_route_retains_session(tmp_path: Path) -> None:
    application = create_app(
        tmp_path / "http-local.db",
        clock=Clock(),
        allowed_origins={"http://127.0.0.1:8000"},
        secure_cookies=False,
    )
    client = TestClient(application, base_url="http://127.0.0.1:8000")

    review_page = client.post("/demo/start")
    assert review_page.status_code == 200
    assert "secure" not in review_page.headers["set-cookie"].lower()
    parser = HiddenInputs()
    parser.feed(review_page.text)
    confirmed = client.post(
        "/confirm-browser",
        data=parser.values,
        headers={"Origin": "http://127.0.0.1:8000"},
    )

    assert confirmed.status_code == 200
    assert "Verified synthetic order" in confirmed.text


def test_public_route_ack_loss_reconciles_one_durable_order(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client, fault=True)
    payload = confirmation_payload(review, confirmation)

    unknown = confirm_evaluation(client, review, confirmation)
    assert unknown.status_code == 202
    assert unknown.json() == {
        "status": "ack_unknown",
        "message": ACK_UNKNOWN_MESSAGE,
        "fault_evidence": "recorded",
    }
    assert "order_id" not in unknown.text

    reconciled = client.get(
        "/api/order-status",
        params={
            "preparation_id": payload["preparation_id"],
            "preparation_digest": payload["preparation_digest"],
            "operation_key": payload["operation_key"],
        },
    )
    assert reconciled.status_code == 200
    receipt = reconciled.json()
    assert receipt["status"] == "complete"
    assert receipt["effect_source"] == "sqlite"
    assert receipt["acknowledgement_loss"] is True
    assert receipt["total_paise"] == 1_500_000

    replay = confirm_evaluation(client, review, confirmation)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "idempotent_replay"
    assert replay.json()["receipt"] == receipt

    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT stock_quantity FROM products WHERE sku = 'KB-ERG-001'"
            ).fetchone()[0]
            == 8
        )
        assert (
            connection.execute(
                "SELECT status FROM preparations WHERE id = ?",
                (payload["preparation_id"],),
            ).fetchone()[0]
            == "consumed"
        )
        assert (
            connection.execute(
                "SELECT consumed_at_epoch FROM confirmation_intents WHERE operation_key = ?",
                (payload["operation_key"],),
            ).fetchone()[0]
            is not None
        )
        assert connection.execute("SELECT COUNT(*) FROM fault_events").fetchone()[0] == 1
        snapshot = connection.execute(
            """
            SELECT pi.product_id, pi.sku, pi.name, pi.quantity,
                   pi.unit_price_paise, pi.product_version, pi.line_total_paise,
                   oi.product_id, oi.sku, oi.name, oi.quantity,
                   oi.unit_price_paise, oi.product_version, oi.line_total_paise
            FROM preparation_items pi
            JOIN orders o ON o.preparation_id = pi.preparation_id
            JOIN order_items oi ON oi.order_id = o.id AND oi.product_id = pi.product_id
            """
        ).fetchone()
        assert tuple(snapshot[:7]) == tuple(snapshot[7:])
        event = connection.execute(
            "SELECT actor, confirmation_method FROM confirmation_events"
        ).fetchone()
        assert tuple(event) == ("scripted_evaluator", "evaluation_api")


def test_browser_ack_unknown_requires_authoritative_status_check(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review = client.post(
        "/demo/start",
        data={
            "brief": "Buy two ergonomic keyboards safely.",
            "simulate_ack_loss": "1",
        },
    )
    parser = HiddenInputs()
    parser.feed(review.text)

    unknown = client.post(
        "/confirm-browser",
        data=parser.values,
        headers={"Origin": "https://testserver"},
    )

    assert unknown.status_code == 202
    assert "Confirmation status unknown" in unknown.text
    assert ACK_UNKNOWN_MESSAGE in unknown.text
    assert 'action="/check-status-browser"' in unknown.text
    assert "order_" not in unknown.text
    status = HiddenInputs()
    status.feed(unknown.text)
    reconciled = client.post(
        "/check-status-browser",
        data=status.values,
        headers={"Origin": "https://testserver"},
    )

    assert reconciled.status_code == 200
    assert "ACK_UNKNOWN reconciled from authoritative state" in reconciled.text
    assert "Verified synthetic order" in reconciled.text
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM fault_events").fetchone()[0] == 1
        )


def test_browser_receipt_failure_can_reconcile_without_retry(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database_path, _clock, _application = orderseal
    review = client.post("/demo/start")
    confirmation = HiddenInputs()
    confirmation.feed(review.text)
    original_receipt = domain_module._receipt_for_order

    def fail_receipt(*_args, **_kwargs) -> dict[str, object]:
        raise RuntimeError("receipt failed")

    monkeypatch.setattr(domain_module, "_receipt_for_order", fail_receipt)

    unknown = client.post(
        "/confirm-browser",
        data=confirmation.values,
        headers={"Origin": "https://testserver"},
    )

    assert unknown.status_code == 202
    assert 'action="/check-status-browser"' in unknown.text
    monkeypatch.setattr(domain_module, "_receipt_for_order", original_receipt)
    status = HiddenInputs()
    status.feed(unknown.text)
    reconciled = client.post(
        "/check-status-browser",
        data=status.values,
        headers={"Origin": "https://testserver"},
    )
    assert reconciled.status_code == 200
    assert "ACK_UNKNOWN reconciled from authoritative state" in reconciled.text
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_concurrent_double_click_commits_once_and_replays_same_receipt(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, application = orderseal
    review, confirmation = start_evaluation(client)
    barrier = Barrier(2)

    def submit() -> dict[str, object]:
        contender = TestClient(application, base_url="https://testserver")
        contender.cookies.update(client.cookies)
        barrier.wait()
        response = confirm_evaluation(contender, review, confirmation)
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in [executor.submit(submit), executor.submit(submit)]
        ]

    assert {result["outcome"] for result in results} == {
        "committed",
        "idempotent_replay",
    }
    assert results[0]["receipt"] == results[1]["receipt"]
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT stock_quantity FROM products WHERE sku = 'KB-ERG-001'"
            ).fetchone()[0]
            == 8
        )


def test_confirmation_rejects_wrong_csrf_without_effect(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)

    response = client.post(
        "/api/evaluation/confirm",
        json=confirmation_payload(review, confirmation),
        headers={"Origin": "https://testserver", "X-CSRF-Token": "wrong-token-value"},
    )

    assert response.status_code == 403
    assert response.json() == {"error": "csrf_invalid"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_confirmation_rejects_stale_quote_without_stock_change(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    with db.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE products
            SET unit_price_paise = unit_price_paise + 100, version = version + 1
            WHERE sku = 'KB-ERG-001'
            """
        )

    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 409
    assert response.json() == {"error": "quote_stale"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT stock_quantity FROM products WHERE sku = 'KB-ERG-001'"
            ).fetchone()[0]
            == 10
        )


def test_confirmation_rejects_product_deactivated_after_review(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    with db.connect(database_path) as connection:
        connection.execute("UPDATE products SET active = 0 WHERE sku = 'KB-ERG-001'")

    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 409
    assert response.json() == {"error": "product_unavailable"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_cart_mutation_and_stored_quote_tamper_fail_closed(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    with db.connect(database_path) as connection:
        preparation = connection.execute(
            "SELECT cart_id FROM preparations WHERE id = ?",
            (review["preparation_id"],),
        ).fetchone()
        connection.execute(
            "UPDATE cart_items SET quantity = 3 WHERE cart_id = ?",
            (preparation["cart_id"],),
        )

    response = confirm_evaluation(client, review, confirmation)
    assert response.status_code == 409
    assert response.json() == {"error": "cart_stale"}

    second_review, second_confirmation = start_evaluation(client)
    with db.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE preparations
            SET quoted_subtotal_paise = quoted_subtotal_paise + 1,
                quoted_total_paise = quoted_total_paise + 1
            WHERE id = ?
            """,
            (second_review["preparation_id"],),
        )
    tampered = confirm_evaluation(client, second_review, second_confirmation)
    assert tampered.status_code == 409
    assert tampered.json() == {"error": "quote_stale"}


@pytest.mark.parametrize(
    ("column", "value"),
    [("version", 2), ("canonical_json", '{"budget_paise":999999999}')],
)
def test_constraint_mutation_breaks_preparation_binding(
    orderseal: tuple[TestClient, Path, Clock, FastAPI], column: str, value: object
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    with db.connect(database_path) as connection:
        connection.execute(f"UPDATE constraint_sets SET {column} = ?", (value,))

    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 409
    assert response.json() == {"error": "constraints_stale"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_exact_expiry_boundary_fails_closed(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    clock.now += 600

    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 409
    assert response.json() == {"error": "preparation_expired"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_exact_session_expiry_boundary_fails_closed(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    session_id = client.cookies.get("orderseal_session")
    with db.connect(database_path) as connection:
        connection.execute(
            "UPDATE sessions SET expires_at_epoch = ? WHERE id = ?",
            (clock.now + 1, session_id),
        )
    clock.now += 1

    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 403
    assert response.json() == {"error": "session_required"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_lock_delay_cannot_commit_an_expired_preparation(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    payload = confirmation_payload(review, confirmation)
    session_id = client.cookies.get("orderseal_session")
    lock_attempted = Event()

    with db.connect(database_path) as lock_connection:
        lock_connection.execute("BEGIN IMMEDIATE")

        def submit_after_lock() -> None:
            with db.connect(database_path) as contender:
                contender.set_trace_callback(
                    lambda statement: (
                        lock_attempted.set() if statement == "BEGIN IMMEDIATE" else None
                    )
                )
                confirm_order(
                    contender,
                    session_id=session_id,
                    preparation_id=payload["preparation_id"],
                    preparation_digest=payload["preparation_digest"],
                    intent_nonce=confirmation["intent_nonce"],
                    operation_key=payload["operation_key"],
                    clock=clock,
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(submit_after_lock)
            assert lock_attempted.wait(timeout=1)
            clock.now += 600
            lock_connection.commit()
            with pytest.raises(DomainError, match="preparation_expired"):
                future.result()

    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_cross_session_status_lookup_does_not_disclose_order(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    first_client, database_path, clock, _application = orderseal
    review, confirmation = start_evaluation(first_client)
    payload = confirmation_payload(review, confirmation)
    committed = confirm_evaluation(first_client, review, confirmation)
    assert committed.status_code == 200

    second_client = TestClient(
        create_app(
            database_path,
            clock=clock,
            eval_mode=True,
            allowed_origins={"https://testserver"},
            secure_cookies=True,
        ),
        base_url="https://testserver",
    )
    start_evaluation(second_client)
    response = second_client.get(
        "/api/order-status",
        params={
            "preparation_id": payload["preparation_id"],
            "preparation_digest": payload["preparation_digest"],
            "operation_key": payload["operation_key"],
        },
    )

    assert response.status_code == 404
    assert response.json() == {"error": "order_not_found"}


def test_new_operation_key_cannot_reuse_consumed_preparation(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    payload = confirmation_payload(review, confirmation)
    assert confirm_evaluation(client, review, confirmation).status_code == 200

    payload["operation_key"] = "op_" + "x" * 24
    replay = client.post(
        "/api/evaluation/confirm",
        json=payload,
        headers=confirmation_headers(confirmation),
    )

    assert replay.status_code == 409
    assert replay.json() == {"error": "preparation_not_pending"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_operation_key_collision_is_generic_and_creates_no_second_order(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    first_client, database_path, clock, _application = orderseal
    first_review, first_confirmation = start_evaluation(first_client)
    first_payload = confirmation_payload(first_review, first_confirmation)
    assert (
        confirm_evaluation(first_client, first_review, first_confirmation).status_code
        == 200
    )

    second_client = TestClient(
        create_app(
            database_path,
            clock=clock,
            eval_mode=True,
            allowed_origins={"https://testserver"},
            secure_cookies=True,
        ),
        base_url="https://testserver",
    )
    second_review, second_confirmation = start_evaluation(second_client)
    second_payload = confirmation_payload(second_review, second_confirmation)
    second_payload["operation_key"] = first_payload["operation_key"]
    collision = second_client.post(
        "/api/evaluation/confirm",
        json=second_payload,
        headers=confirmation_headers(second_confirmation),
    )

    assert collision.status_code == 409
    assert collision.json() == {"error": "confirmation_conflict"}
    assert "order_id" not in collision.text
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_wrong_origin_and_non_eval_routes_fail_closed(
    orderseal: tuple[TestClient, Path, Clock, FastAPI], tmp_path: Path
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    missing_origin = client.post(
        "/api/evaluation/confirm",
        json=confirmation_payload(review, confirmation),
        headers={"X-CSRF-Token": confirmation["csrf_token"]},
    )
    assert missing_origin.status_code == 403
    assert missing_origin.json() == {"error": "origin_forbidden"}
    response = client.post(
        "/api/evaluation/confirm",
        json=confirmation_payload(review, confirmation),
        headers={
            "Origin": "https://attacker.invalid",
            "X-CSRF-Token": confirmation["csrf_token"],
        },
    )
    assert response.status_code == 403
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0

    non_eval = TestClient(create_app(tmp_path / "non-eval.db"))
    assert non_eval.post("/api/evaluation/start", json={}).status_code == 403


def test_fault_event_write_failure_remains_structured_unknown(
    orderseal: tuple[TestClient, Path, Clock, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client, fault=True)

    def fail_fault_write(*_args, **_kwargs) -> None:
        raise RuntimeError("synthetic fault-event write failure")

    monkeypatch.setattr(main_module, "record_acknowledgement_loss", fail_fault_write)
    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 202
    assert response.json()["status"] == "ack_unknown"
    assert response.json()["fault_evidence"] == "missing"
    assert "order_id" not in response.text
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM fault_events").fetchone()[0] == 0
        )


def test_receipt_failure_after_commit_returns_structured_unknown(
    orderseal: tuple[TestClient, Path, Clock, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)

    def fail_receipt(*_args, **_kwargs) -> dict[str, object]:
        raise RuntimeError("synthetic receipt failure")

    monkeypatch.setattr(domain_module, "_receipt_for_order", fail_receipt)
    response = confirm_evaluation(client, review, confirmation)

    assert response.status_code == 202
    assert response.json() == {
        "status": "ack_unknown",
        "message": ACK_UNKNOWN_MESSAGE,
    }
    assert "order_id" not in response.text
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_lock_timeout_returns_structured_busy_without_effect(
    orderseal: tuple[TestClient, Path, Clock, FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    monkeypatch.setattr(db, "BUSY_TIMEOUT_MS", 20)

    with db.connect(database_path) as lock_connection:
        lock_connection.execute("BEGIN IMMEDIATE")
        response = confirm_evaluation(client, review, confirmation)
        lock_connection.rollback()

    assert response.status_code == 503
    assert response.json() == {"error": "confirmation_busy"}
    with db.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_replay_cannot_rewrite_acknowledged_history(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, _clock, _application = orderseal
    review, confirmation = start_evaluation(client)
    first = confirm_evaluation(client, review, confirmation)
    replay = confirm_evaluation(client, review, confirmation)

    assert first.status_code == replay.status_code == 200
    assert first.json()["receipt"] == replay.json()["receipt"]
    with db.connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM fault_events").fetchone()[0] == 0
        )


def test_schema_rejects_cross_session_graphs_and_invalid_totals(
    orderseal: tuple[TestClient, Path, Clock, FastAPI],
) -> None:
    client, database_path, clock, _application = orderseal
    start_evaluation(client)
    start_evaluation(client)
    with db.connect(database_path) as connection:
        sessions = connection.execute(
            "SELECT id FROM sessions ORDER BY created_at_epoch, id"
        ).fetchall()
        first_session, second_session = sessions[0]["id"], sessions[1]["id"]
        second_cart = connection.execute(
            "SELECT id FROM carts WHERE session_id = ?", (second_session,)
        ).fetchone()["id"]
        second_constraints = connection.execute(
            "SELECT id FROM constraint_sets WHERE session_id = ?", (second_session,)
        ).fetchone()["id"]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO preparations VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "prep_cross_session_123",
                    first_session,
                    second_cart,
                    2,
                    second_constraints,
                    1,
                    "a" * 64,
                    "b" * 64,
                    "c" * 64,
                    "synthetic-inr-v1",
                    0,
                    0,
                    0,
                    0,
                    clock.now + 100,
                    "invalidated",
                    clock.now,
                ),
            )

        preparation_id = connection.execute(
            "SELECT id FROM preparations LIMIT 1"
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE preparations SET quoted_total_paise = quoted_total_paise + 1 WHERE id = ?",
                (preparation_id,),
            )


def test_preparation_digest_is_stable_across_item_order() -> None:
    items = [
        {
            "product_id": "product-b",
            "sku": "B",
            "quantity": 1,
            "unit_price_paise": 200,
            "delivery_days": 2,
            "product_version": 1,
            "active": 1,
        },
        {
            "product_id": "product-a",
            "sku": "A",
            "quantity": 2,
            "unit_price_paise": 100,
            "delivery_days": 1,
            "product_version": 3,
            "active": 1,
        },
    ]
    first = digest(
        "orderseal-preparation-v1",
        preparation_payload(
            cart_id="cart_abcdefghijklmnop",
            cart_digest="a" * 64,
            cart_version=1,
            constraint_digest="b" * 64,
            constraint_set_version=1,
            constraints={"budget_paise": 500},
            expires_at_epoch=1234,
            items=items,
            subtotal_paise=400,
            shipping_paise=0,
            tax_paise=0,
        ),
    )
    second = digest(
        "orderseal-preparation-v1",
        preparation_payload(
            cart_id="cart_abcdefghijklmnop",
            cart_digest="a" * 64,
            cart_version=1,
            constraint_digest="b" * 64,
            constraint_set_version=1,
            constraints={"budget_paise": 500},
            expires_at_epoch=1234,
            items=list(reversed(items)),
            subtotal_paise=400,
            shipping_paise=0,
            tax_paise=0,
        ),
    )

    assert first == second
