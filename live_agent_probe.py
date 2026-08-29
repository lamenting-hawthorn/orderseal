from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from app import db
from app.agent import SUPPORTED_BRIEF, OpenRouterCaller, investigate_exact_sku
from gate_zero import load_settings

ROOT = Path(__file__).resolve().parent
RECEIPT_FILE = ROOT / "PHASE2_LIVE_RECEIPT.json"


def _candidate_hashes() -> dict[str, str]:
    return {
        relative_path: hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        for relative_path in ("app/agent.py", "app/domain.py", "live_agent_probe.py")
    }


def main() -> int:
    settings = load_settings()
    caller = OpenRouterCaller(
        base_url=settings["ORDERSEAL_BASE_URL"],
        model=settings["ORDERSEAL_MODEL"],
        api_key=settings["ORDERSEAL_API_KEY"],
    )
    with tempfile.TemporaryDirectory(prefix="orderseal-live-agent-") as directory:
        database_path = Path(directory) / "agent.db"
        db.reset(database_path)
        with db.connect(database_path) as connection:
            outcome = investigate_exact_sku(
                connection,
                SUPPORTED_BRIEF,
                caller,
                clock=lambda: int(time.time()),
            )
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
        "candidate_sha256": _candidate_hashes(),
        "provider_base_url": settings["ORDERSEAL_BASE_URL"].rstrip("/"),
        "model": outcome.model,
        "ok": outcome.status == "ready_for_confirmation",
        "status": outcome.status,
        "reason": outcome.reason,
        "prepared": outcome.prepared,
        "tools": [event["tool"] for event in outcome.trajectory],
        "usage": outcome.usage,
    }
    RECEIPT_FILE.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if outcome.status == "ready_for_confirmation" else 1


if __name__ == "__main__":
    raise SystemExit(main())
