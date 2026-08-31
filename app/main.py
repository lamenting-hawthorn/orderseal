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
SUPPORTED_DEMO_BRIEF = (
    "Buy two ergonomic keyboards under INR 18,000, delivered within five days."
)
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


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    preparation_id: BoundedString
    preparation_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
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
    application.state.allowed_origins = (
        allowed_origins
        if allowed_origins is not None
        else {"http://127.0.0.1:8000"}
    )
    application.state.secure_cookies = secure_cookies

    @application.exception_handler(DomainError)
    async def domain_error_handler(
        request: Request, error: DomainError
    ) -> Response:
        if request.url.path in {"/confirm-browser", "/check-status-browser"}:
            return HTMLResponse(_held_page(error.code), status_code=error.status_code)
        return JSONResponse({"error": error.code}, status_code=error.status_code)

    @application.exception_handler(AcknowledgementUnknown)
    async def acknowledgement_unknown_handler(
        request: Request, _error: AcknowledgementUnknown
    ) -> Response:
        if request.url.path == "/confirm-browser":
            return HTMLResponse(_held_page("ack_unknown"), status_code=202)
        return JSONResponse(
            {"status": "ack_unknown", "message": ACK_UNKNOWN_MESSAGE},
            status_code=202,
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        fault_toggle = ""
        if application.state.eval_mode:
            fault_toggle = """<label class="check"><input type="checkbox" name="simulate_ack_loss" value="1"> Demonstrate post-commit acknowledgement loss</label>"""
        return HTMLResponse(_home_page(fault_toggle))

    @application.post("/demo/start", response_class=HTMLResponse)
    async def start_browser_demo(request: Request) -> HTMLResponse:
        brief, simulate_ack_loss = _parse_start_form(await request.body())
        if simulate_ack_loss and not application.state.eval_mode:
            raise DomainError("evaluation_mode_required", 403)
        with db.connect(application.state.database_path) as connection:
            prepared = prepare_demo(
                connection,
                application.state.clock(),
                actor="browser_operator_unverified",
                confirmation_method="browser_ui",
                fault_kind="post_commit_ack_loss" if simulate_ack_loss else None,
            )
        response = HTMLResponse(_review_page(prepared, brief))
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
        try:
            result = _confirm(application, session_id, confirmation)
        except AcknowledgementUnknown:
            return HTMLResponse(
                _ack_unknown_page(confirmation, csrf_token), status_code=202
            )
        fault_evidence = _deliver_assigned_fault(application, result)
        if fault_evidence is not None:
            return HTMLResponse(
                _ack_unknown_page(confirmation, csrf_token),
                status_code=202,
            )
        return HTMLResponse(_receipt_page(result))

    @application.post("/check-status-browser", response_class=HTMLResponse)
    async def check_status_browser(request: Request) -> HTMLResponse:
        session_id = _session_id(application, request)
        _validate_origin(application, request.headers.get("origin"))
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if content_type != "application/x-www-form-urlencoded":
            raise DomainError("status_form_invalid", 400)
        status, csrf_token = _parse_status_form(await request.body())
        _validate_csrf(application, session_id, csrf_token)
        with db.connect(application.state.database_path) as connection:
            receipt = reconcile_order(
                connection,
                session_id=session_id,
                preparation_id=status.preparation_id,
                preparation_digest=status.preparation_digest,
                operation_key=status.operation_key,
            )
        return HTMLResponse(_receipt_page(receipt, recovered=True))

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


def _parse_start_form(body: bytes) -> tuple[str, bool]:
    if not body:
        return SUPPORTED_DEMO_BRIEF, False
    if len(body) > 4_096:
        raise DomainError("brief_invalid", 400)
    try:
        values = parse_qs(
            body.decode("utf-8"),
            strict_parsing=True,
            keep_blank_values=True,
            max_num_fields=2,
        )
        if set(values) - {"brief", "simulate_ack_loss"} or set(values) < {"brief"}:
            raise ValueError
        if any(len(value) != 1 for value in values.values()):
            raise ValueError
        brief = values["brief"][0].strip()
        if not 1 <= len(brief) <= 500 or any(
            ord(character) < 32 and character not in "\n\r\t" for character in brief
        ):
            raise ValueError
        if brief != SUPPORTED_DEMO_BRIEF:
            raise DomainError("brief_unsupported", 400)
        fault_value = values.get("simulate_ack_loss", [None])[0]
        if fault_value not in {None, "1"}:
            raise ValueError
        simulate_ack_loss = fault_value == "1"
    except DomainError:
        raise
    except (UnicodeDecodeError, ValueError):
        raise DomainError("brief_invalid", 400) from None
    return brief, simulate_ack_loss


def _parse_status_form(body: bytes) -> tuple[StatusRequest, str]:
    if len(body) > 8_192:
        raise DomainError("status_form_invalid", 400)
    try:
        values = parse_qs(
            body.decode("ascii"),
            strict_parsing=True,
            keep_blank_values=True,
            max_num_fields=4,
        )
        expected = {
            "preparation_id",
            "preparation_digest",
            "operation_key",
            "csrf_token",
        }
        if set(values) != expected or any(len(value) != 1 for value in values.values()):
            raise ValueError
        status = StatusRequest.model_validate(
            {key: values[key][0] for key in expected - {"csrf_token"}}
        )
    except (UnicodeDecodeError, ValueError, ValidationError):
        raise DomainError("status_form_invalid", 400) from None
    return status, values["csrf_token"][0]


def _set_session_cookie(response: Response, session_id: str, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=3_600,
    )


def _home_page(fault_toggle: str) -> str:
    return _document(
        "OrderSeal",
        f"""<p class="eyebrow">Synthetic checkout safety demo</p><h1>OrderSeal</h1>
<p>Describe the constrained purchase. The model-facing workflow may investigate and prepare, but only this browser can confirm the exact reviewed order.</p>
<form method="post" action="/demo/start"><label for="brief">Procurement brief</label>
<select id="brief" name="brief" required autofocus><option>{html.escape(SUPPORTED_DEMO_BRIEF)}</option></select>
{fault_toggle}<button type="submit">Build evidence-backed review</button></form>
<p class="note">This local demo supports the one brief shown above. Synthetic catalogue and money only; no payment or real commerce connection.</p>""",
    )


def _review_page(prepared: PreparedDemo, brief: str = "Synthetic demo brief") -> str:
    review = prepared.review
    item_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['name'])}</td>"
        f"<td><code>{html.escape(item['sku'])}</code></td>"
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
    return _document(
        "OrderSeal review",
        f"""<p class="eyebrow">Evidence review</p><h1>Review exact synthetic order</h1>
<section aria-labelledby="brief-heading"><h2 id="brief-heading">Your brief</h2><p class="brief">{html.escape(brief)}</p></section>
<p role="status" aria-live="polite" class="ok">Budget proven · delivery proven · stock proven</p>
<table><caption>Prepared items</caption><thead><tr><th scope="col">Item</th><th scope="col">SKU</th><th scope="col">Qty</th><th scope="col">Unit INR</th><th scope="col">Stock</th><th scope="col">Delivery</th></tr></thead><tbody>{item_rows}</tbody></table>
<p class="total">Total INR {_format_inr(review["total_paise"])}</p>
<p>Review expires at epoch {review["expires_at_epoch"]}.</p>
<details><summary>Preparation digest</summary><code>{html.escape(prepared.preparation_digest)}</code></details>
<div class="warning"><strong>Human-only boundary.</strong> This final action commits one synthetic order. The investigation agent cannot call it.</div>
<form method="post" action="/confirm-browser">{hidden_fields}<button class="danger" type="submit">Confirm exact synthetic order</button></form>""",
    )


def _ack_unknown_page(confirmation: ConfirmationRequest, csrf_token: str) -> str:
    hidden = {
        "preparation_id": confirmation.preparation_id,
        "preparation_digest": confirmation.preparation_digest,
        "operation_key": confirmation.operation_key,
        "csrf_token": csrf_token,
    }
    fields = "".join(
        f'<input type="hidden" name="{name}" value="{html.escape(value, quote=True)}">'
        for name, value in hidden.items()
    )
    return _document(
        "OrderSeal status unknown",
        f"""<p class="eyebrow">Recovery required</p><h1>Confirmation status unknown</h1>
<p role="status" aria-live="assertive" class="warning">{html.escape(ACK_UNKNOWN_MESSAGE)}</p>
<p>The acknowledgement was lost after the commit boundary. Check the authoritative SQLite record; do not create another order.</p>
<form method="post" action="/check-status-browser">{fields}<button autofocus type="submit">Check authoritative status</button></form>""",
    )


def _receipt_page(
    result: ConfirmationResult | dict[str, object], *, recovered: bool = False
) -> str:
    receipt = result.receipt if isinstance(result, ConfirmationResult) else result
    total_paise = receipt["total_paise"]
    if type(total_paise) is not int:
        raise ValueError("invalid receipt total")
    recovery = (
        '<p role="status" aria-live="polite" class="ok">ACK_UNKNOWN reconciled from authoritative state.</p>'
        if recovered
        else '<p role="status" aria-live="polite" class="ok">Commit acknowledged.</p>'
    )
    return _document(
        "OrderSeal receipt",
        f"""<p class="eyebrow">Verified receipt</p><h1>Verified synthetic order</h1>{recovery}
<dl><dt>Order</dt><dd><code>{html.escape(str(receipt["order_id"]))}</code></dd><dt>Total</dt><dd>INR {_format_inr(total_paise)}</dd><dt>Effect source</dt><dd>Authoritative SQLite</dd></dl>
<p class="note">This receipt proves one local synthetic effect, not a real payment or production transaction.</p>""",
    )


def _held_page(reason: str) -> str:
    message = ACK_UNKNOWN_MESSAGE if reason == "ack_unknown" else f"Held safely: {reason}"
    return _document(
        "OrderSeal held",
        f"""<p class="eyebrow">No new action authorized</p><h1>Order held</h1><p role="alert" class="warning">{html.escape(message)}</p><p><a href="/">Start a new review</a></p>""",
    )


def _document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>{html.escape(title)}</title>
<style>:root{{color-scheme:light;--ink:#16241f;--muted:#53645d;--paper:#f4f0e7;--card:#fffdf8;--green:#176b52;--line:#d8d2c4;--warn:#fff0c7}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:17px/1.55 system-ui,sans-serif}}main{{width:min(760px,calc(100% - 32px));margin:5vh auto;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:clamp(24px,5vw,52px);box-shadow:0 18px 60px #243b3020}}h1{{font:700 clamp(2.2rem,7vw,4.8rem)/.95 Georgia,serif;margin:.2em 0 .35em}}h2{{font-size:1.1rem}}.eyebrow{{color:var(--green);font-weight:800;letter-spacing:.09em;text-transform:uppercase}}label{{display:block;font-weight:750;margin:.8rem 0 .35rem}}select{{width:100%;padding:14px;border:1px solid #8d9a94;border-radius:10px;background:white;font:inherit}}button{{margin-top:1rem;border:0;border-radius:999px;background:var(--green);color:white;padding:.8rem 1.2rem;font:700 1rem system-ui;cursor:pointer}}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{{outline:4px solid #e6a700;outline-offset:3px}}.check{{font-weight:500}}.check input{{margin-right:.45rem}}.note{{color:var(--muted);font-size:.92rem}}.brief,.warning,.ok{{padding:14px;border-radius:10px}}.brief{{background:#eef1eb}}.warning{{background:var(--warn);border-left:5px solid #bd6b00}}.ok{{background:#e4f4ec;color:#0f5a43}}table{{width:100%;border-collapse:collapse;display:block;overflow-x:auto}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}.total{{font:700 1.5rem Georgia,serif}}code{{overflow-wrap:anywhere}}dt{{font-weight:750}}dd{{margin:0 0 1rem}}</style></head>
<body><main id="main" tabindex="-1">{body}</main><script>document.getElementById('main').focus({{preventScroll:true}})</script></body></html>"""


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
