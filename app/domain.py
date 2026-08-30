from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PRICING_POLICY_VERSION = "synthetic-inr-v1"
PREPARATION_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 3_600
DEMO_SKU = "KB-ERG-001"
DEMO_QUANTITY = 2
DEMO_CONSTRAINTS = {
    "budget_paise": 1_800_000,
    "currency": "INR",
    "delivery_days_max": 5,
    "items": [{"quantity": DEMO_QUANTITY, "sku": DEMO_SKU}],
}


class DomainError(Exception):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class AcknowledgementUnknown(Exception):
    """A durable order may exist, but its response could not be constructed."""


@dataclass(frozen=True)
class PreparedDemo:
    session_id: str
    csrf_token: str
    preparation_id: str
    preparation_digest: str
    intent_nonce: str
    operation_key: str
    review: dict[str, Any]


@dataclass(frozen=True)
class ConfirmationResult:
    receipt: dict[str, Any]
    fresh_commit: bool
    fault_kind: str | None


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(domain: str, value: object) -> str:
    encoded = f"{domain}\0{canonical_json(value)}".encode()
    return hashlib.sha256(encoded).hexdigest()


def hash_capability(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def preparation_payload(
    *,
    cart_id: str,
    cart_digest: str,
    cart_version: int,
    constraint_digest: str,
    constraint_set_version: int,
    constraints: dict[str, Any],
    expires_at_epoch: int,
    items: list[dict[str, Any]],
    subtotal_paise: int,
    shipping_paise: int,
    tax_paise: int,
) -> dict[str, Any]:
    total_paise = subtotal_paise + shipping_paise + tax_paise
    return {
        "cart_digest": cart_digest,
        "cart_id": cart_id,
        "cart_version": cart_version,
        "constraint_digest": constraint_digest,
        "constraint_set_version": constraint_set_version,
        "constraints": constraints,
        "expires_at_epoch": expires_at_epoch,
        "items": [
            {
                "delivery_days": item["delivery_days"],
                "active": item["active"],
                "product_id": item["product_id"],
                "product_version": item["product_version"],
                "quantity": item["quantity"],
                "sku": item["sku"],
                "unit_price_paise": item["unit_price_paise"],
            }
            for item in sorted(items, key=lambda item: item["sku"])
        ],
        "pricing_policy_version": PRICING_POLICY_VERSION,
        "shipping_paise": shipping_paise,
        "subtotal_paise": subtotal_paise,
        "tax_paise": tax_paise,
        "total_paise": total_paise,
    }


def prepare_demo(
    connection: sqlite3.Connection,
    now_epoch: int,
    *,
    actor: str,
    confirmation_method: str,
    fault_kind: str | None = None,
) -> PreparedDemo:
    if actor not in {"browser_operator_unverified", "scripted_evaluator"}:
        raise ValueError("invalid confirmation actor")
    if confirmation_method not in {"browser_ui", "evaluation_api"}:
        raise ValueError("invalid confirmation method")
    if fault_kind not in {None, "post_commit_ack_loss"}:
        raise ValueError("invalid fault kind")
    session_id = random_id("ses")
    csrf_token = secrets.token_urlsafe(32)
    constraint_set_id = random_id("cst")
    cart_id = random_id("cart")
    preparation_id = random_id("prep")
    intent_nonce = secrets.token_urlsafe(32)
    operation_key = random_id("op")
    expires_at_epoch = now_epoch + PREPARATION_TTL_SECONDS

    constraints = json.loads(canonical_json(DEMO_CONSTRAINTS))
    constraint_json = canonical_json(constraints)
    constraint_digest = digest("orderseal-constraints-v1", constraints)
    product = connection.execute(
        """
        SELECT id, sku, name, unit_price_paise, stock_quantity,
               delivery_days, version, active
        FROM products WHERE sku = ?
        """,
        (DEMO_SKU,),
    ).fetchone()
    if product is None or not product["active"]:
        raise DomainError("product_unavailable")

    quantity = DEMO_QUANTITY
    if product["stock_quantity"] < quantity:
        raise DomainError("insufficient_stock")
    if product["delivery_days"] is None:
        raise DomainError("delivery_unproven")

    item = {
        "product_id": product["id"],
        "sku": product["sku"],
        "name": product["name"],
        "quantity": quantity,
        "unit_price_paise": product["unit_price_paise"],
        "stock_quantity": product["stock_quantity"],
        "delivery_days": product["delivery_days"],
        "product_version": product["version"],
        "active": product["active"],
        "line_total_paise": product["unit_price_paise"] * quantity,
    }
    items = [item]
    subtotal_paise = item["line_total_paise"]
    shipping_paise = 0
    tax_paise = 0
    total_paise = subtotal_paise + shipping_paise + tax_paise
    if total_paise > constraints["budget_paise"]:
        raise DomainError("budget_exceeded")
    if item["delivery_days"] > constraints["delivery_days_max"]:
        raise DomainError("delivery_deadline_unmet")

    cart_digest = digest(
        "orderseal-cart-v1",
        [{"product_id": item["product_id"], "quantity": quantity}],
    )
    prepared_payload = preparation_payload(
        cart_id=cart_id,
        cart_digest=cart_digest,
        cart_version=1,
        constraint_digest=constraint_digest,
        constraint_set_version=1,
        constraints=constraints,
        expires_at_epoch=expires_at_epoch,
        items=items,
        subtotal_paise=subtotal_paise,
        shipping_paise=shipping_paise,
        tax_paise=tax_paise,
    )
    preparation_digest = digest("orderseal-preparation-v1", prepared_payload)

    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?)",
            (
                session_id,
                hash_capability(csrf_token),
                now_epoch + SESSION_TTL_SECONDS,
                now_epoch,
            ),
        )
        connection.execute(
            "INSERT INTO constraint_sets VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                constraint_set_id,
                session_id,
                1,
                constraint_json,
                constraint_digest,
                "[]",
                now_epoch,
            ),
        )
        connection.execute(
            "INSERT INTO carts VALUES (?, ?, ?, ?, ?)",
            (cart_id, session_id, 1, "prepared", now_epoch),
        )
        connection.execute(
            "INSERT INTO cart_items VALUES (?, ?, ?)",
            (cart_id, product["id"], quantity),
        )
        connection.execute(
            """
            INSERT INTO preparations VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                preparation_id,
                session_id,
                cart_id,
                1,
                constraint_set_id,
                1,
                cart_digest,
                constraint_digest,
                preparation_digest,
                PRICING_POLICY_VERSION,
                subtotal_paise,
                shipping_paise,
                tax_paise,
                total_paise,
                expires_at_epoch,
                "pending",
                now_epoch,
            ),
        )
        connection.execute(
            """
            INSERT INTO preparation_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                preparation_id,
                item["product_id"],
                item["sku"],
                item["name"],
                item["quantity"],
                item["unit_price_paise"],
                item["stock_quantity"],
                item["delivery_days"],
                item["product_version"],
                item["active"],
                item["line_total_paise"],
            ),
        )
        connection.execute(
            """
            INSERT INTO confirmation_intents VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL
            )
            """,
            (
                hash_capability(intent_nonce),
                session_id,
                preparation_id,
                preparation_digest,
                1,
                constraint_set_id,
                operation_key,
                actor,
                confirmation_method,
                fault_kind,
                expires_at_epoch,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return PreparedDemo(
        session_id=session_id,
        csrf_token=csrf_token,
        preparation_id=preparation_id,
        preparation_digest=preparation_digest,
        intent_nonce=intent_nonce,
        operation_key=operation_key,
        review={
            "preparation_id": preparation_id,
            "preparation_digest": preparation_digest,
            "expires_at_epoch": expires_at_epoch,
            "items": items,
            "subtotal_paise": subtotal_paise,
            "shipping_paise": shipping_paise,
            "tax_paise": tax_paise,
            "total_paise": total_paise,
            "constraints": [
                {"name": "budget", "state": "proven"},
                {"name": "delivery", "state": "proven"},
                {"name": "stock", "state": "proven"},
            ],
        },
    )


def get_review(
    connection: sqlite3.Connection, session_id: str, preparation_id: str
) -> dict[str, Any]:
    preparation = connection.execute(
        """
        SELECT * FROM preparations WHERE id = ? AND session_id = ?
        """,
        (preparation_id, session_id),
    ).fetchone()
    if preparation is None:
        raise DomainError("preparation_not_found", 404)
    items = connection.execute(
        "SELECT * FROM preparation_items WHERE preparation_id = ? ORDER BY sku",
        (preparation_id,),
    ).fetchall()
    return {
        "preparation_id": preparation["id"],
        "preparation_digest": preparation["preparation_digest"],
        "expires_at_epoch": preparation["expires_at_epoch"],
        "status": preparation["status"],
        "items": [dict(item) for item in items],
        "subtotal_paise": preparation["quoted_subtotal_paise"],
        "shipping_paise": preparation["quoted_shipping_paise"],
        "tax_paise": preparation["quoted_tax_paise"],
        "total_paise": preparation["quoted_total_paise"],
    }


def confirm_order(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    preparation_id: str,
    preparation_digest: str,
    intent_nonce: str,
    operation_key: str,
    clock: Callable[[], int],
) -> ConfirmationResult:
    try:
        connection.execute("BEGIN IMMEDIATE")
        now_epoch = clock()
        existing = connection.execute(
            "SELECT * FROM orders WHERE operation_key = ?",
            (operation_key,),
        ).fetchone()
        if existing is not None:
            exact_match = (
                existing["session_id"] == session_id
                and existing["preparation_id"] == preparation_id
                and existing["preparation_digest"] == preparation_digest
            )
            if not exact_match:
                raise DomainError("confirmation_conflict")
            connection.execute(
                """
                INSERT INTO confirmation_attempts (
                    session_id, preparation_id, operation_key, outcome, created_at_epoch
                ) VALUES (?, ?, ?, 'idempotent_replay', ?)
                """,
                (session_id, preparation_id, operation_key, now_epoch),
            )
            connection.commit()
            return ConfirmationResult(
                receipt=_receipt_after_effect(connection, existing["id"]),
                fresh_commit=False,
                fault_kind=None,
            )

        preparation = connection.execute(
            """
            SELECT * FROM preparations
            WHERE id = ? AND session_id = ? AND preparation_digest = ?
            """,
            (preparation_id, session_id, preparation_digest),
        ).fetchone()
        if preparation is None:
            raise DomainError("confirmation_conflict")
        if preparation["status"] != "pending":
            raise DomainError("preparation_not_pending")
        if now_epoch >= preparation["expires_at_epoch"]:
            raise DomainError("preparation_expired")

        intent = connection.execute(
            """
            SELECT * FROM confirmation_intents
            WHERE nonce_hash = ? AND session_id = ? AND preparation_id = ?
              AND preparation_digest = ? AND cart_version = ?
              AND constraint_set_id = ? AND operation_key = ?
            """,
            (
                hash_capability(intent_nonce),
                session_id,
                preparation_id,
                preparation_digest,
                preparation["cart_version"],
                preparation["constraint_set_id"],
                operation_key,
            ),
        ).fetchone()
        if intent is None or intent["consumed_at_epoch"] is not None:
            raise DomainError("confirmation_intent_invalid")
        if now_epoch >= intent["expires_at_epoch"]:
            raise DomainError("confirmation_intent_expired")

        session = connection.execute(
            "SELECT expires_at_epoch FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None or now_epoch >= session["expires_at_epoch"]:
            raise DomainError("session_expired", 403)

        cart = connection.execute(
            "SELECT * FROM carts WHERE id = ? AND session_id = ?",
            (preparation["cart_id"], session_id),
        ).fetchone()
        if cart is None or cart["version"] != preparation["cart_version"]:
            raise DomainError("cart_stale")

        live_cart_rows = connection.execute(
            """
            SELECT product_id, quantity FROM cart_items
            WHERE cart_id = ? ORDER BY product_id
            """,
            (preparation["cart_id"],),
        ).fetchall()
        live_cart_items = [
            {"product_id": row["product_id"], "quantity": row["quantity"]}
            for row in live_cart_rows
        ]
        live_cart_digest = digest("orderseal-cart-v1", live_cart_items)
        if live_cart_digest != preparation["cart_digest"]:
            raise DomainError("cart_stale")

        constraints_row = connection.execute(
            "SELECT * FROM constraint_sets WHERE id = ? AND session_id = ?",
            (preparation["constraint_set_id"], session_id),
        ).fetchone()
        if constraints_row is None:
            raise DomainError("constraints_missing")
        try:
            constraints = json.loads(constraints_row["canonical_json"])
        except json.JSONDecodeError as error:
            raise DomainError("constraints_stale") from error
        if not isinstance(constraints, dict):
            raise DomainError("constraints_stale")
        live_constraint_digest = digest("orderseal-constraints-v1", constraints)
        if (
            constraints_row["version"] != preparation["constraint_set_version"]
            or live_constraint_digest != constraints_row["constraint_digest"]
            or live_constraint_digest != preparation["constraint_digest"]
        ):
            raise DomainError("constraints_stale")

        snapshot_rows = connection.execute(
            "SELECT * FROM preparation_items WHERE preparation_id = ? ORDER BY product_id",
            (preparation_id,),
        ).fetchall()
        if not snapshot_rows:
            raise DomainError("preparation_empty")
        snapshot_cart_items = [
            {"product_id": row["product_id"], "quantity": row["quantity"]}
            for row in snapshot_rows
        ]
        if snapshot_cart_items != live_cart_items:
            raise DomainError("cart_stale")

        current_items: list[dict[str, Any]] = []
        for snapshot in snapshot_rows:
            product = connection.execute(
                "SELECT * FROM products WHERE id = ?",
                (snapshot["product_id"],),
            ).fetchone()
            if product is None or not product["active"]:
                raise DomainError("product_unavailable")
            if (
                snapshot["active"] != 1
                or product["version"] != snapshot["product_version"]
                or product["unit_price_paise"] != snapshot["unit_price_paise"]
                or product["delivery_days"] != snapshot["delivery_days"]
                or product["active"] != snapshot["active"]
            ):
                raise DomainError("quote_stale")
            if product["stock_quantity"] < snapshot["quantity"]:
                raise DomainError("insufficient_stock")
            current_items.append(dict(snapshot))

        subtotal_paise = sum(item["line_total_paise"] for item in current_items)
        shipping_paise = preparation["quoted_shipping_paise"]
        tax_paise = preparation["quoted_tax_paise"]
        total_paise = subtotal_paise + shipping_paise + tax_paise
        if (
            preparation["pricing_policy_version"] != PRICING_POLICY_VERSION
            or preparation["quoted_subtotal_paise"] != subtotal_paise
            or preparation["quoted_shipping_paise"] != shipping_paise
            or preparation["quoted_tax_paise"] != tax_paise
            or preparation["quoted_total_paise"] != total_paise
        ):
            raise DomainError("quote_stale")
        recomputed = preparation_payload(
            cart_id=preparation["cart_id"],
            cart_digest=live_cart_digest,
            cart_version=preparation["cart_version"],
            constraint_digest=live_constraint_digest,
            constraint_set_version=constraints_row["version"],
            constraints=constraints,
            expires_at_epoch=preparation["expires_at_epoch"],
            items=current_items,
            subtotal_paise=subtotal_paise,
            shipping_paise=shipping_paise,
            tax_paise=tax_paise,
        )
        if digest("orderseal-preparation-v1", recomputed) != preparation_digest:
            raise DomainError("preparation_digest_mismatch")
        if total_paise > constraints["budget_paise"]:
            raise DomainError("budget_exceeded")
        if any(
            item["delivery_days"] is None
            or item["delivery_days"] > constraints["delivery_days_max"]
            for item in current_items
        ):
            raise DomainError("delivery_deadline_unmet")

        confirmation_event_id = random_id("approval")
        order_id = random_id("ord")
        connection.execute(
            """
            INSERT INTO confirmation_events VALUES (
                ?, ?, ?, ?, 'approved', ?, ?, ?
            )
            """,
            (
                confirmation_event_id,
                session_id,
                preparation_id,
                preparation["cart_digest"],
                intent["actor"],
                intent["confirmation_method"],
                now_epoch,
            ),
        )
        connection.execute(
            """
            INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                session_id,
                preparation_id,
                operation_key,
                preparation_digest,
                subtotal_paise,
                shipping_paise,
                tax_paise,
                total_paise,
                confirmation_event_id,
                now_epoch,
            ),
        )
        for item in current_items:
            connection.execute(
                "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    item["product_id"],
                    item["sku"],
                    item["name"],
                    item["quantity"],
                    item["unit_price_paise"],
                    item["product_version"],
                    item["line_total_paise"],
                ),
            )
            updated = connection.execute(
                """
                UPDATE products SET stock_quantity = stock_quantity - ?
                WHERE id = ? AND version = ? AND active = 1
                  AND stock_quantity >= ?
                """,
                (
                    item["quantity"],
                    item["product_id"],
                    item["product_version"],
                    item["quantity"],
                ),
            )
            if updated.rowcount != 1:
                raise DomainError("stock_update_conflict")

        connection.execute(
            "UPDATE preparations SET status = 'consumed' WHERE id = ? AND status = 'pending'",
            (preparation_id,),
        )
        connection.execute(
            "UPDATE carts SET status = 'consumed', updated_at_epoch = ? WHERE id = ?",
            (now_epoch, preparation["cart_id"]),
        )
        connection.execute(
            "UPDATE confirmation_intents SET consumed_at_epoch = ? WHERE nonce_hash = ?",
            (now_epoch, intent["nonce_hash"]),
        )
        connection.execute(
            """
            INSERT INTO confirmation_attempts (
                session_id, preparation_id, operation_key, outcome, created_at_epoch
            ) VALUES (?, ?, ?, 'committed', ?)
            """,
            (session_id, preparation_id, operation_key, now_epoch),
        )
        connection.commit()
        return ConfirmationResult(
            receipt=_receipt_after_effect(connection, order_id),
            fresh_commit=True,
            fault_kind=intent["fault_kind"],
        )
    except AcknowledgementUnknown:
        raise
    except DomainError:
        connection.rollback()
        raise
    except sqlite3.IntegrityError as error:
        connection.rollback()
        raise DomainError("confirmation_conflict") from error
    except sqlite3.OperationalError as error:
        connection.rollback()
        if (
            getattr(error, "sqlite_errorcode", None)
            in {
                sqlite3.SQLITE_BUSY,
                sqlite3.SQLITE_LOCKED,
            }
            or "locked" in str(error).lower()
        ):
            raise DomainError("confirmation_busy", 503) from error
        raise
    except Exception:
        connection.rollback()
        raise


def record_acknowledgement_loss(
    connection: sqlite3.Connection, order_id: str, now_epoch: int
) -> None:
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT OR IGNORE INTO fault_events
                (id, order_id, kind, delivered_after_commit, created_at_epoch)
            VALUES (?, ?, 'post_commit_ack_loss', 1, ?)
            """,
            (random_id("fault"), order_id, now_epoch),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def reconcile_order(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    preparation_id: str,
    preparation_digest: str,
    operation_key: str,
) -> dict[str, Any]:
    order = connection.execute(
        """
        SELECT id FROM orders
        WHERE session_id = ? AND preparation_id = ?
          AND preparation_digest = ? AND operation_key = ?
        """,
        (session_id, preparation_id, preparation_digest, operation_key),
    ).fetchone()
    if order is None:
        raise DomainError("order_not_found", 404)
    return _receipt_for_order(connection, order["id"])


def _receipt_for_order(connection: sqlite3.Connection, order_id: str) -> dict[str, Any]:
    order = connection.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    if order is None:
        raise DomainError("order_not_found", 404)
    items = connection.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY sku",
        (order_id,),
    ).fetchall()
    fault = connection.execute(
        "SELECT kind, delivered_after_commit FROM fault_events WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    return {
        "status": "complete",
        "order_id": order["id"],
        "preparation_id": order["preparation_id"],
        "preparation_digest": order["preparation_digest"],
        "items": [dict(item) for item in items],
        "subtotal_paise": order["subtotal_paise"],
        "shipping_paise": order["shipping_paise"],
        "tax_paise": order["tax_paise"],
        "total_paise": order["total_paise"],
        "confirmed_at_epoch": order["confirmed_at_epoch"],
        "acknowledgement_loss": fault is not None,
        "effect_source": "sqlite",
    }


def _receipt_after_effect(
    connection: sqlite3.Connection, order_id: str
) -> dict[str, Any]:
    try:
        return _receipt_for_order(connection, order_id)
    except Exception as error:
        raise AcknowledgementUnknown from error


def displayed_cart(
    connection: sqlite3.Connection, *, sku: str, quantity: int
) -> dict[str, Any]:
    if not 1 <= quantity <= 1_000:
        raise DomainError("quantity_invalid")
    product = connection.execute(
        """
        SELECT id, sku, name, unit_price_paise, stock_quantity,
               delivery_days, version, active
        FROM products WHERE sku = ?
        """,
        (sku,),
    ).fetchone()
    if product is None or not product["active"]:
        raise DomainError("product_unavailable")
    if product["stock_quantity"] < quantity:
        raise DomainError("insufficient_stock")
    subtotal_paise = product["unit_price_paise"] * quantity
    snapshot = {
        "sku": product["sku"],
        "name": product["name"],
        "quantity": quantity,
        "unit_price_paise": product["unit_price_paise"],
        "product_version": product["version"],
        "delivery_days": product["delivery_days"],
        "shipping_paise": 0,
        "tax_paise": 0,
        "total_paise": subtotal_paise,
    }
    return {
        **snapshot,
        "displayed_cart_digest": digest("orderseal-displayed-cart-v1", snapshot),
    }


def create_evaluation_session(
    connection: sqlite3.Connection, now_epoch: int
) -> str:
    session_id = random_id("ses")
    discarded_csrf = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?)",
        (
            session_id,
            hash_capability(discarded_csrf),
            now_epoch + SESSION_TTL_SECONDS,
            now_epoch,
        ),
    )
    return session_id


def record_evaluation_approval(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    condition: str,
    session_id: str,
    displayed_cart_digest: str,
    decision: str,
    actor: str,
    displayed_at_monotonic_ms: int,
    decided_at_monotonic_ms: int,
    server_received_at_epoch: int,
) -> str:
    if condition not in {"directbuy", "orderseal"}:
        raise ValueError("invalid evaluation condition")
    if decision not in {"approved", "rejected"}:
        raise ValueError("invalid approval decision")
    if actor not in {"browser_operator_unverified", "scripted_evaluator"}:
        raise ValueError("invalid approval actor")
    approval_event_id = random_id("evalapproval")
    connection.execute(
        """
        INSERT INTO evaluation_approval_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            approval_event_id,
            run_id,
            condition,
            hash_capability(session_id),
            displayed_cart_digest,
            decision,
            actor,
            displayed_at_monotonic_ms,
            decided_at_monotonic_ms,
            server_received_at_epoch,
        ),
    )
    return approval_event_id


def record_evaluation_fault_delivery(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    condition: str,
    order_id: str,
    commit_observed_monotonic_ms: int,
    injector_triggered_monotonic_ms: int,
    acknowledgement_suppressed_monotonic_ms: int,
    response_returned_monotonic_ms: int,
) -> str:
    if condition not in {"directbuy", "orderseal"}:
        raise ValueError("invalid evaluation condition")
    event_id = random_id("evalfault")
    connection.execute(
        """
        INSERT INTO evaluation_fault_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            run_id,
            condition,
            hash_capability(order_id),
            commit_observed_monotonic_ms,
            injector_triggered_monotonic_ms,
            acknowledgement_suppressed_monotonic_ms,
            response_returned_monotonic_ms,
        ),
    )
    return event_id
