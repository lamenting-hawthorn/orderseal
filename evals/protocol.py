from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from app.domain import canonical_json

PROTOCOL_VERSION = "orderseal-eval-v1"
ASSIGNMENT_SEED = 20260830
PROVIDER_NAME = "openrouter"
PROVIDER_BASE_URL = "https://openrouter.ai/api/v1"
PROVIDER_MODEL_ID = "deepseek/deepseek-v4-flash-0731"
PROVIDER_CANONICAL_MODEL_ID = "deepseek/deepseek-v4-flash-20260731"
UPSTREAM_PROVIDER = "baidu/fp8"
PROVIDER_ALLOW_FALLBACKS = False
PROVIDER_REQUIRE_PARAMETERS = True
CONDITIONS = ("directbuy", "orderseal")
CASE_IDS = tuple(f"C{number:02d}" for number in range(1, 13))
ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "cases.jsonl"
EXPECTATIONS_PATH = ROOT / "expectations.json"
CASE_KEYS = {
    "case_id",
    "request",
    "stratum",
    "clarification_script",
    "mutation_profile",
    "fault_profile",
    "adversary",
}
EXPECTATION_KEYS = {
    "expected_effect",
    "allowed_terminal_states",
    "allowed_skus",
    "quantity",
    "max_total_paise",
    "max_delivery_days",
    "approval_required",
    "reconciliation_required",
}


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line, object_pairs_hook=_object_without_duplicate_keys)
        if not isinstance(row, dict):
            raise ValueError(f"case line {line_number} must be an object")
        if set(row) != CASE_KEYS:
            raise ValueError(f"case line {line_number} has an invalid schema")
        for key in (
            "case_id",
            "request",
            "stratum",
            "mutation_profile",
            "fault_profile",
            "adversary",
        ):
            if not isinstance(row[key], str) or not 1 <= len(row[key]) <= 2_000:
                raise ValueError(f"case line {line_number} has invalid {key}")
        clarification = row["clarification_script"]
        if clarification is not None and (
            not isinstance(clarification, dict)
            or set(clarification) != {"answer", "maximum_questions"}
            or not isinstance(clarification["answer"], str)
            or not 1 <= len(clarification["answer"]) <= 2_000
            or any(ord(character) < 32 for character in clarification["answer"])
            or type(clarification["maximum_questions"]) is not int
            or clarification["maximum_questions"] != 1
        ):
            raise ValueError(
                f"case line {line_number} has invalid clarification_script"
            )
        rows.append(row)
    case_ids = tuple(row.get("case_id") for row in rows)
    if case_ids != CASE_IDS:
        raise ValueError("case manifest must contain ordered exact IDs C01-C12")
    return rows


def load_expectations(path: Path = EXPECTATIONS_PATH) -> dict[str, dict[str, Any]]:
    parsed = json.loads(
        path.read_text(), object_pairs_hook=_object_without_duplicate_keys
    )
    if not isinstance(parsed, dict) or tuple(parsed) != CASE_IDS:
        raise ValueError("expectations must contain ordered exact IDs C01-C12")
    for case_id, expectation in parsed.items():
        if not isinstance(expectation, dict) or set(expectation) != EXPECTATION_KEYS:
            raise ValueError(f"expectation {case_id} has an invalid schema")
        if expectation["expected_effect"] not in {
            "COMMIT_ONE",
            "COMMIT_ONE_AFTER_CLARIFY",
            "COMMIT_ONE_AFTER_REVIEW",
            "COMMIT_ONE_RECONCILED",
            "NO_COMMIT",
        }:
            raise ValueError(f"expectation {case_id} has an invalid effect")
        if not isinstance(expectation["allowed_terminal_states"], list) or not all(
            terminal in {"complete", "held", "needs_user"}
            for terminal in expectation["allowed_terminal_states"]
        ):
            raise ValueError(f"expectation {case_id} has invalid terminals")
        if not isinstance(expectation["allowed_skus"], list) or not all(
            isinstance(sku, str) and 1 <= len(sku) <= 80
            for sku in expectation["allowed_skus"]
        ):
            raise ValueError(f"expectation {case_id} has invalid SKUs")
        for key in ("quantity", "max_total_paise", "max_delivery_days"):
            value = expectation[key]
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"expectation {case_id} has invalid {key}")
        if any(
            type(expectation[key]) is not bool
            for key in ("approval_required", "reconciliation_required")
        ):
            raise ValueError(f"expectation {case_id} has invalid flags")
    return parsed


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_assignments(seed: int = ASSIGNMENT_SEED) -> list[dict[str, Any]]:
    randomizer = random.Random(seed)
    first_condition = {case_id: randomizer.choice(CONDITIONS) for case_id in CASE_IDS}
    blocks: list[tuple[str, int, tuple[str, str]]] = []
    for case_id in CASE_IDS:
        first = first_condition[case_id]
        second = CONDITIONS[1] if first == CONDITIONS[0] else CONDITIONS[0]
        blocks.append((case_id, 1, (first, second)))
        blocks.append((case_id, 2, (second, first)))
    randomizer.shuffle(blocks)

    assignments: list[dict[str, Any]] = []
    for block_index, (case_id, repeat, order) in enumerate(blocks, start=1):
        pair_id = f"{case_id}-R{repeat}"
        for within_block_order, condition in enumerate(order, start=1):
            assignment_index = len(assignments) + 1
            assignments.append(
                {
                    "run_id": f"run-{assignment_index:03d}-{pair_id}-{condition}",
                    "pair_id": pair_id,
                    "case_id": case_id,
                    "repeat": repeat,
                    "condition": condition,
                    "block_index": block_index,
                    "within_block_order": within_block_order,
                    "scheduled": True,
                    "denominator_included": True,
                }
            )
    return assignments


def assignment_bytes(seed: int = ASSIGNMENT_SEED) -> bytes:
    rows = "".join(f"{canonical_json(row)}\n" for row in build_assignments(seed))
    return rows.encode()


def write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"refusing to rewrite frozen artifact: {path}")
        return
    path.write_bytes(content)
