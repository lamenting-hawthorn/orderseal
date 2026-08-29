from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
RECEIPT_FILE = ROOT / "GATE_ZERO_RECEIPT.json"
EXPECTED_KEYS = {"ORDERSEAL_BASE_URL", "ORDERSEAL_MODEL", "ORDERSEAL_API_KEY"}


def load_settings() -> dict[str, str]:
    settings: dict[str, str] = {}
    for line_number, raw_line in enumerate(ENV_FILE.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in EXPECTED_KEYS or key in settings:
            raise ValueError(f"invalid .env entry on line {line_number}")
        settings[key] = value.strip()

    missing = EXPECTED_KEYS - settings.keys()
    if missing or not all(settings.values()):
        raise ValueError(f"missing required setting names: {sorted(missing)}")
    return settings


def main() -> int:
    settings = load_settings()
    base_url = settings["ORDERSEAL_BASE_URL"].rstrip("/")
    parsed_url = urlparse(base_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("ORDERSEAL_BASE_URL must be an absolute HTTPS URL")

    payload = {
        "model": settings["ORDERSEAL_MODEL"],
        "messages": [
            {
                "role": "system",
                "content": "Call the supplied function exactly once. Do not answer in prose.",
            },
            {
                "role": "user",
                "content": "Record the harmless Gate Zero probe.",
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "record_probe",
                    "description": "Record a harmless tool-calling capability probe.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "enum": ["gate-zero-ok"]}
                        },
                        "required": ["message"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "record_probe"}},
        "parallel_tool_calls": False,
        "temperature": 0,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={
            "Authorization": f"Bearer {settings['ORDERSEAL_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "OrderSeal-GateZero/1.0",
        },
        method="POST",
    )

    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            request, timeout=30, context=ssl.create_default_context()
        ) as response:
            raw_response = response.read(1_000_000)
            status = response.status
    except urllib.error.HTTPError as error:
        provider_error: dict[str, object] = {}
        try:
            error_data = json.loads(error.read(65_536))
            error_object = error_data.get("error") if isinstance(error_data, dict) else None
            if isinstance(error_object, dict):
                for key in ("type", "code"):
                    if isinstance(error_object.get(key), (str, int)):
                        provider_error[key] = error_object[key]
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "provider_http_error",
                    "status": error.code,
                    "provider_error": provider_error,
                }
            )
        )
        return 1
    except (urllib.error.URLError, TimeoutError):
        print(json.dumps({"ok": False, "error": "provider_transport_error"}))
        return 1

    latency_ms = round((time.monotonic() - started) * 1000)
    response_data = json.loads(raw_response)
    function_call = response_data["choices"][0]["message"]["tool_calls"][0]["function"]
    arguments = json.loads(function_call["arguments"])
    if function_call["name"] != "record_probe" or arguments != {"message": "gate-zero-ok"}:
        print(json.dumps({"ok": False, "error": "invalid_tool_call", "status": status}))
        return 1

    usage = response_data.get("usage") or {}
    receipt = {
        "schema_version": 1,
        "ok": True,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "provider_base_url": base_url,
        "endpoint": "/chat/completions",
        "model_requested": settings["ORDERSEAL_MODEL"],
        "model_returned": response_data.get("model"),
        "latency_ms": latency_ms,
        "tool_name": "record_probe",
        "tool_arguments": arguments,
        "usage": {
            key: usage[key]
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(usage.get(key), int)
        },
        "response_sha256": hashlib.sha256(raw_response).hexdigest(),
    }
    RECEIPT_FILE.write_text(json.dumps(receipt, indent=2, sort_keys=True) + os.linesep)
    print(json.dumps({"ok": True, "model": receipt["model_returned"], "latency_ms": latency_ms}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": type(error).__name__}))
        raise SystemExit(1) from None
