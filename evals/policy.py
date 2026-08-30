from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent import CandidatePolicy
from evals.protocol import CASE_IDS, sha256_file

POLICIES_PATH = Path(__file__).with_name("policies.json")
POLICY_KEYS = {
    "allowed_skus",
    "budget_paise",
    "clarification_required",
    "delivery_days_max",
    "fallback_from_skus",
    "ordering_allowed",
    "quantity",
    "selection_rule",
    "shipping_paise",
    "tax_paise",
    "terminal_without_effect",
}


def _without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_policy_inputs(path: Path = POLICIES_PATH) -> dict[str, dict[str, Any]]:
    parsed = json.loads(
        path.read_text(), object_pairs_hook=_without_duplicate_keys
    )
    if not isinstance(parsed, dict) or tuple(parsed) != CASE_IDS:
        raise ValueError("policy inputs must contain ordered exact IDs C01-C12")
    for case_id, row in parsed.items():
        if not isinstance(row, dict) or set(row) != POLICY_KEYS:
            raise ValueError(f"policy input {case_id} has an invalid schema")
        if (
            type(row["clarification_required"]) is not bool
            or type(row["ordering_allowed"]) is not bool
            or not isinstance(row["allowed_skus"], list)
            or not all(isinstance(sku, str) for sku in row["allowed_skus"])
            or not isinstance(row["fallback_from_skus"], list)
            or not all(
                isinstance(sku, str) for sku in row["fallback_from_skus"]
            )
        ):
            raise ValueError(f"policy input {case_id} has invalid primitive fields")
        CandidatePolicy(
            allowed_skus=tuple(row["allowed_skus"]),
            quantity=row["quantity"],
            budget_paise=row["budget_paise"],
            delivery_days_max=row["delivery_days_max"],
            fallback_from_skus=tuple(row["fallback_from_skus"]),
            ordering_allowed=row["ordering_allowed"],
            terminal_without_effect=row["terminal_without_effect"],
            shipping_paise=row["shipping_paise"],
            tax_paise=row["tax_paise"],
            selection_rule=row["selection_rule"],
            source_digest=sha256_file(path),
        )
    return parsed


def candidate_policy_for_case(
    case_id: str, *, clarified: bool = False, path: Path = POLICIES_PATH
) -> CandidatePolicy:
    rows = load_policy_inputs(path)
    try:
        row = rows[case_id]
    except KeyError as error:
        raise ValueError("unknown case policy") from error
    source_digest = sha256_file(path)
    if row["clarification_required"] and not clarified:
        return CandidatePolicy(
            allowed_skus=(),
            quantity=None,
            budget_paise=None,
            delivery_days_max=None,
            ordering_allowed=False,
            terminal_without_effect="needs_user",
            source_digest=source_digest,
        )
    return CandidatePolicy(
        allowed_skus=tuple(row["allowed_skus"]),
        quantity=row["quantity"],
        budget_paise=row["budget_paise"],
        delivery_days_max=row["delivery_days_max"],
        fallback_from_skus=tuple(row["fallback_from_skus"]),
        ordering_allowed=row["ordering_allowed"],
        terminal_without_effect=row["terminal_without_effect"],
        shipping_paise=row["shipping_paise"],
        tax_paise=row["tax_paise"],
        selection_rule=row["selection_rule"],
        source_digest=source_digest,
    )
