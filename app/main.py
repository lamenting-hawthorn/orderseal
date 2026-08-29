from __future__ import annotations

import hashlib
import hmac
import html
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app import db
from app.domain import (
    AcknowledgementUnknown,
    ConfirmationResult,
    DomainError,
    PreparedDemo,
    confirm_order,
    prepare_demo,
    reconcile_order,
    record_acknowledgement_loss,
)

SESSION_COOKIE = "orderseal_session"
ACK_UNKNOWN_MESSAGE = (
    "Confirmation status is unknown. We are checking the authoritative order record. "
    "Do not submit again."
)
BoundedString = Annotated[str, StringConstraints(min_length=16, max_length=160)]


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    preparation_id: BoundedString
    preparation_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    intent_nonce: BoundedString
    operation_key: BoundedString


class EvaluationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    fault_kind: Literal["post_commit_ack_loss"] | None = None


def create_app(
    database_path: str | Path = "orderseal.db",
    *,
    clock: Callable[[], int] | None = None,
    eval_mode: bool = False,
    allowed_origins: set[str] | None = None,
    secure_cookies: bool = False,
) -> FastAPI:
    db.initialize(database_path)
    db.seed(database_path)
    application = FastAPI(title="OrderSeal", version="0.1.0")
    application.state.database_path = str(database_path)
    application.state.clock = clock or (lambda: int(time.time()))
    application.state.eval_mode = eval_mode
    application.state.allowed_origins = allowed_origins or {"http://127.0.0.1:8000"}
    application.state.secure_cookies = secure_cookies

    @application.exception_handler(DomainError)
    async def domain_error_handler(
        _request: Request, error: DomainError
    ) -> JSONResponse:
        return JSONResponse({"error": error.code}, status_code=error.status_code)

    @application.exception_handler(AcknowledgementUnknown)
    async def acknowledgement_unknown_handler(
        request: Request, _error: AcknowledgementUnknown
    ) -> Response:
        if request.url.path == "/confirm-browser":
            return HTMLResponse(
                f"<h1>Confirmation status unknown</h1><p>{html.escape(ACK_UNKNOWN_MESSAGE)}</p>",
                status_code=202,
            )
        return JSONResponse(
            {"status": "ack_unknown", "message": ACK_UNKNOWN_MESSAGE},
            status_code=202,
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        return HTMLResponse(
            """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OrderSeal</title></head>
<body><main><h1>OrderSeal</h1><p>Prepare one synthetic, constrained order.</p>
<form method="post" action="/demo/start"><button type="submit">Prepare synthetic order</button></form>
</main></body></html>"""
        )

    @application.post("/demo/start", response_class=HTMLResponse)
    def start_browser_demo() -> HTMLResponse:
        with db.connect(application.state.database_path) as connection:
            prepared = prepare_demo(
                connection,
                application.state.clock(),
                actor="browser_operator_unverified",
                confirmation_method="browser_ui",
            )
        response = HTMLResponse(_review_page(prepared))
        _set_session_cookie(
            response, prepared.session_id, application.state.secure_cookies
        )
        return response

    @application.post("/confirm-browser", response_class=HTMLResponse)
    async def confirm_browser(request: Request) -> HTMLResponse:
        session_id = _session_id(application, request)
        _validate_origin(application, request.headers.get("origin"))
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if content_type != "application/x-www-form-urlencoded":
            raise DomainError("confirmation_form_invalid", 400)
        confirmation, csrf_token = _parse_confirmation_form(await request.body())
        _validate_csrf(application, session_id, csrf_token)
        result = _confirm(application, session_id, confirmation)
        fault_evidence = _deliver_assigned_fault(application, result)
        if fault_evidence is not None:
            return HTMLResponse(
                f"<h1>Confirmation status unknown</h1><p>{html.escape(ACK_UNKNOWN_MESSAGE)}</p>",
                status_code=202,
            )
        return HTMLResponse(_receipt_page(result))

    @application.post("/api/evaluation/start")
    def start_evaluation(
        start: EvaluationStartRequest | None = None,
    ) -> JSONResponse:
        if not application.state.eval_mode:
            raise DomainError("evaluation_mode_required", 403)
        fault_kind = start.fault_kind if start is not None else None
        with db.connect(application.state.database_path) as connection:
            prepared = prepare_demo(
                connection,
                application.state.clock(),
                actor="scripted_evaluator",
                confirmation_method="evaluation_api",
                fault_kind=fault_kind,
            )
        response = JSONResponse(
            {
                "review": prepared.review,
                "confirmation": {
                    "csrf_token": prepared.csrf_token,
                    "intent_nonce": prepared.intent_nonce,
                    "operation_key": prepared.operation_key,
                },
            }
        )
        _set_session_cookie(
            response, prepared.session_id, application.state.secure_cookies
        )
        return response

    @application.post("/api/evaluation/confirm")
    def confirm_evaluation(
        confirmation: ConfirmationRequest,
        request: Request,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        origin: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        if not application.state.eval_mode:
            raise DomainError("evaluation_mode_required", 403)
        session_id = _session_id(application, request)
        _validate_origin(application, origin)
        _validate_csrf(application, session_id, csrf_token)
        result = _confirm(application, session_id, confirmation)
        fault_evidence = _deliver_assigned_fault(application, result)
        if fault_evidence is not None:
            return JSONResponse(
                {
                    "status": "ack_unknown",
                    "message": ACK_UNKNOWN_MESSAGE,
                    "fault_evidence": fault_evidence,
                },
                status_code=202,
            )
        return JSONResponse(
            {
                "outcome": "committed" if result.fresh_commit else "idempotent_replay",
                "receipt": result.receipt,
            }
        )

    @application.get("/api/order-status")
    def order_status(
        request: Request,
        preparation_id: BoundedString,
        preparation_digest: Annotated[
            str, StringConstraints(pattern=r"^[0-9a-f]{64}$")
        ],
        operation_key: BoundedString,
    ) -> JSONResponse:
        session_id = _session_id(application, request)
        with db.connect(application.state.database_path) as connection:
            receipt = reconcile_order(
                connection,
                session_id=session_id,
                preparation_id=preparation_id,
                preparation_digest=preparation_digest,
                operation_key=operation_key,
            )
        return JSONResponse(receipt)

    return application


def _confirm(
    application: FastAPI,
    session_id: str,
    confirmation: ConfirmationRequest,
) -> ConfirmationResult:
    with db.connect(application.state.database_path) as connection:
        return confirm_order(
            connection,
            session_id=session_id,
            preparation_id=confirmation.preparation_id,
            preparation_digest=confirmation.preparation_digest,
            intent_nonce=confirmation.intent_nonce,
            operation_key=confirmation.operation_key,
            clock=application.state.clock,
        )


def _deliver_assigned_fault(
    application: FastAPI, result: ConfirmationResult
) -> str | None:
    if not result.fresh_commit or result.fault_kind != "post_commit_ack_loss":
        return None
    try:
        with db.connect(application.state.database_path) as connection:
            record_acknowledgement_loss(
                connection, result.receipt["order_id"], application.state.clock()
            )
    # Any failure after the durable commit must remain an uncertain acknowledgement.
    except Exception:  # noqa: BLE001
        return "missing"
    return "recorded"


def _session_id(application: FastAPI, request: Request) -> str:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id or len(session_id) > 160:
        raise DomainError("session_required", 403)
    with db.connect(application.state.database_path) as connection:
        session = connection.execute(
            "SELECT expires_at_epoch FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if session is None or application.state.clock() >= session["expires_at_epoch"]:
        raise DomainError("session_required", 403)
    return session_id


def _validate_origin(application: FastAPI, origin: str | None) -> None:
    if origin not in application.state.allowed_origins:
        raise DomainError("origin_forbidden", 403)


def _validate_csrf(
    application: FastAPI, session_id: str, csrf_token: str | None
) -> None:
    if csrf_token is None or len(csrf_token) > 160:
        raise DomainError("csrf_invalid", 403)
    supplied_hash = hashlib.sha256(csrf_token.encode()).hexdigest()
    with db.connect(application.state.database_path) as connection:
        session = connection.execute(
            "SELECT csrf_token_hash, expires_at_epoch FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if (
        session is None
        or application.state.clock() >= session["expires_at_epoch"]
        or not hmac.compare_digest(supplied_hash, session["csrf_token_hash"])
    ):
        raise DomainError("csrf_invalid", 403)


def _parse_confirmation_form(body: bytes) -> tuple[ConfirmationRequest, str]:
    if len(body) > 8_192:
        raise DomainError("confirmation_form_invalid", 400)
    try:
        values = parse_qs(
            body.decode("ascii"),
            strict_parsing=True,
            keep_blank_values=True,
            max_num_fields=5,
        )
        expected = {
            "preparation_id",
            "preparation_digest",
            "intent_nonce",
            "operation_key",
            "csrf_token",
        }
        if set(values) != expected or any(len(value) != 1 for value in values.values()):
            raise ValueError
        confirmation = ConfirmationRequest.model_validate(
            {key: values[key][0] for key in expected - {"csrf_token"}}
        )
        csrf_token = values["csrf_token"][0]
    except (UnicodeDecodeError, ValueError, ValidationError):
        raise DomainError("confirmation_form_invalid", 400) from None
    return confirmation, csrf_token


def _set_session_cookie(response: Response, session_id: str, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=3_600,
    )


def _review_page(prepared: PreparedDemo) -> str:
    review = prepared.review
    item_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['name'])}</td>"
        f"<td>{html.escape(item['sku'])}</td>"
        f"<td>{item['quantity']}</td>"
        f"<td>{_format_inr(item['unit_price_paise'])}</td>"
        f"<td>{item['stock_quantity']}</td>"
        f"<td>{item['delivery_days']} days</td>"
        "</tr>"
        for item in review["items"]
    )
    hidden = {
        "preparation_id": prepared.preparation_id,
        "preparation_digest": prepared.preparation_digest,
        "intent_nonce": prepared.intent_nonce,
        "operation_key": prepared.operation_key,
        "csrf_token": prepared.csrf_token,
    }
    hidden_fields = "".join(
        f'<input type="hidden" name="{name}" value="{html.escape(value, quote=True)}">'
        for name, value in hidden.items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OrderSeal review</title></head>
<body><main><h1>Review exact synthetic order</h1>
<p>Deterministic facts: budget proven; delivery proven; stock proven.</p>
<table><caption>Prepared items</caption><thead><tr><th>Item</th><th>SKU</th><th>Qty</th><th>Unit INR</th><th>Stock</th><th>Delivery</th></tr></thead><tbody>{item_rows}</tbody></table>
<p><strong>Total INR {_format_inr(review["total_paise"])}</strong></p>
<p>Expires at {review["expires_at_epoch"]}</p>
<details><summary>Preparation reference</summary><code>{html.escape(prepared.preparation_digest)}</code></details>
<form method="post" action="/confirm-browser">{hidden_fields}<button type="submit">Confirm exact synthetic order</button></form>
</main></body></html>"""


def _receipt_page(result: ConfirmationResult) -> str:
    receipt = result.receipt
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OrderSeal receipt</title></head>
<body><main><h1>Verified synthetic order</h1><p>Order {html.escape(receipt["order_id"])}</p>
<p>Total INR {_format_inr(receipt["total_paise"])}</p><p>Effect source: SQLite</p></main></body></html>"""


def _format_inr(paise: int) -> str:
    rupees, remainder = divmod(paise, 100)
    return f"{rupees:,}.{remainder:02d}"


default_origin = os.environ.get("ORDERSEAL_ORIGIN", "http://127.0.0.1:8000")
app = create_app(
    os.environ.get("ORDERSEAL_DB_PATH", "orderseal.db"),
    eval_mode=os.environ.get("ORDERSEAL_EVAL_MODE") == "1",
    allowed_origins={default_origin},
    secure_cookies=default_origin.startswith("https://"),
)
