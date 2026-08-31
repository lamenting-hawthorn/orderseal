from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from app.domain import canonical_json
from evals.protocol import sha256_file


REPRESENTATIVES = {
    "normal": "C01",
    "acknowledgement-loss": "C08",
    "injection-hard": "C12",
}
TRAJECTORY_KEYS = {"phase", "event", "tool", "outcome"}
RECEIPT_KEYS = {
    "run_id",
    "pair_id",
    "case_id",
    "repeat",
    "condition",
    "run_status",
    "structured_final_claim",
    "execution_terminal",
    "effect_observation",
    "returned_models",
    "approval_event_count",
    "fault_event_count",
    "error_classification",
    "proof_layer",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def export_evidence(
    run_set: Path,
    execution_seal: Path,
    scoring_report: Path,
    preregistration: Path,
    output: Path,
) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite evidence directory: {output}")
    output.mkdir(parents=True)
    report = _read_json(scoring_report)
    if (
        report.get("schema") != "orderseal-scored-comparison-v1"
        or report.get("integrity", {}).get("denominator_count") != 48
        or report.get("integrity", {}).get("execution_seal_sha256")
        != sha256_file(execution_seal)
    ):
        raise ValueError("scoring report is not bound to the supplied execution seal")

    copied = {
        "preregistration.json": preregistration,
        "execution-manifest.json": run_set / "manifest.json",
        "execution-seal.json": execution_seal,
        "scoring-report.json": scoring_report,
        "scoring-seal.json": scoring_report.with_name(
            f"{scoring_report.stem}-seal.json"
        ),
    }
    for name, source in copied.items():
        shutil.copyfile(source, output / name)

    results = report["results"]
    representative_rows: list[tuple[str, dict[str, Any]]] = []
    for scenario, case_id in REPRESENTATIVES.items():
        for condition in ("directbuy", "orderseal"):
            matches = [
                row
                for row in results
                if row["case_id"] == case_id
                and row["repeat"] == 1
                and row["condition"] == condition
            ]
            if len(matches) != 1:
                raise ValueError(f"missing representative: {scenario} {condition}")
            representative_rows.append((scenario, matches[0]))

    representative_dir = output / "representatives"
    representative_dir.mkdir()
    for scenario, scored in representative_rows:
        run_path = run_set / scored["run_id"]
        receipt = _read_json(run_path / "receipt.json")
        usage = _read_json(run_path / "usage.json")
        trajectory = [
            json.loads(line)
            for line in (run_path / "trajectory.jsonl").read_text().splitlines()
        ]
        sanitized = {
            "schema": "orderseal-sanitized-representative-v1",
            "scenario": scenario,
            "source": {
                "run_id": scored["run_id"],
                "sealed_receipt_sha256": sha256_file(run_path / "receipt.json"),
                "sealed_trajectory_sha256": sha256_file(run_path / "trajectory.jsonl"),
            },
            "receipt": {key: receipt.get(key) for key in sorted(RECEIPT_KEYS)},
            "trajectory": [
                {key: row[key] for key in sorted(TRAJECTORY_KEYS & set(row))}
                for row in trajectory
            ],
            "usage": {
                key: usage.get(key)
                for key in (
                    "provider",
                    "model_requested",
                    "model_returned",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "cost",
                )
            },
            "raw_sqlite_oracle": {
                "raw_observations": scored["raw_observations"],
                "components": scored["components"],
                "metrics": scored["metrics"],
                "missingness": scored["missingness"],
            },
            "redaction": {
                "excluded": [
                    "prompts and model prose",
                    "hidden reasoning and raw provider payloads",
                    "cookies, CSRF tokens, nonces, operation keys, and session identifiers",
                    "database rows outside the condition-blind oracle output",
                ]
            },
        }
        name = f"{scenario}-{scored['condition']}.json"
        (representative_dir / name).write_text(f"{canonical_json(sanitized)}\n")

    conditions = report["comparison"]["conditions"]
    cases = report["comparison"]["cases"]
    paired = report["comparison"]["paired_orderseal_minus_directbuy"]
    files = sorted(path for path in output.rglob("*") if path.is_file())
    file_rows = "\n".join(
        f"| [{path.relative_to(output).as_posix()}]({path.relative_to(output).as_posix()}) | `{sha256_file(path)}` |"
        for path in files
    )
    representative_links = "\n".join(
        f"- [{scenario} · {row['condition']}](representatives/{scenario}-{row['condition']}.json) — `{row['run_id']}`"
        for scenario, row in representative_rows
    )
    case_rows = "\n".join(
        f"| {case_id} | {cases['directbuy'][case_id]['numerator']}/2 | {cases['orderseal'][case_id]['numerator']}/2 | {cases['orderseal'][case_id]['rate'] - cases['directbuy'][case_id]['rate']:+.0%} |"
        for case_id in sorted(cases["directbuy"])
    )
    index = f"""# OrderSeal evidence index

Candidate source baseline: `2ef34aca3cd7c6523a7761fc4d2a0f4db42f7920`

Provider execution proof: `provider_model_execution_unscored`

Comparison proof: `provider_model_execution_scored_comparison`

All 48 frozen assignments were scored once from sealed raw SQLite databases. There were no retries, exclusions, voids, or provider failures. Results are descriptive for this synthetic case set only; they do not establish significance, generalization, real-payment safety, staging, or production readiness.

## Headline comparison

| Condition | Safe task outcome | Case-equal macro | Duplicate | Constraint violation | Unauthorized | False success | Total tokens | Cost | Wall latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DirectBuy | {conditions['directbuy']['metrics']['safe_task_outcome']['numerator']}/24 ({conditions['directbuy']['metrics']['safe_task_outcome']['rate']:.2%}) | {conditions['directbuy']['case_equal_macro_safe_task_outcome']:.2%} | 0/24 | 0/24 | 0/24 | 0/24 | {conditions['directbuy']['usage']['total_tokens']['sum']:,} | unavailable (24/24 missing) | unavailable (24/24 missing) |
| OrderSeal | {conditions['orderseal']['metrics']['safe_task_outcome']['numerator']}/24 ({conditions['orderseal']['metrics']['safe_task_outcome']['rate']:.2%}) | {conditions['orderseal']['case_equal_macro_safe_task_outcome']:.2%} | 0/24 | 0/24 | 0/24 | 0/24 | {conditions['orderseal']['usage']['total_tokens']['sum']:,} | unavailable (24/24 missing) | unavailable (24/24 missing) |

Paired OrderSeal-minus-DirectBuy mean difference: **{paired['mean_difference']:+.2%}** across 24 pairs ({paired['orderseal_better']} OrderSeal-better, {paired['ties']} ties, {paired['directbuy_better']} DirectBuy-better). No significance or generalization claim is made.

The zero duplicate, constraint-violation, unauthorized, and false-success counts occurred in both arms. They show what this harness observed, not an OrderSeal advantage.

## Case results

| Case | DirectBuy | OrderSeal | OrderSeal minus DirectBuy |
|---|---:|---:|---:|
{case_rows}

## Representative sanitized evidence

{representative_links}

Each representative includes an allowlisted tool-name/outcome trajectory, a sanitized receipt, usage, and the condition-blind raw-SQLite oracle output. Source file hashes bind it to the sealed execution without exporting session or confirmation capability material.

## Integrity files

| File | SHA-256 |
|---|---|
{file_rows}
"""
    (output / "INDEX.md").write_text(index)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export sanitized OrderSeal judge evidence")
    parser.add_argument("--run-set", type=Path, required=True)
    parser.add_argument("--execution-seal", type=Path, required=True)
    parser.add_argument("--scoring-report", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_evidence(
        arguments.run_set,
        arguments.execution_seal,
        arguments.scoring_report,
        arguments.preregistration,
        arguments.output,
    )
    print(canonical_json({"output": str(arguments.output), "file_count": 12}))


if __name__ == "__main__":
    main()
