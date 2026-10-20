"""Pip's clarified 1.0 gate: 13 supported types; 1040 is best-effort only."""
import argparse
import json
from pathlib import Path

from benchmarks.taxclaw_accuracy.runner import digest, write_json


def build(root, runs):
    report = {"application_revision": "533760d94d43bd7c93bf10e09e3f5f84eb55e510",
              "gate_scope": "13 README-supported types, clean AND degraded; 1040 excluded as best-effort by Pip clarification",
              "scorer": "Unchanged strict scorer; all fields, JSON types, extras and container shape count",
              "haiku_transport": "Frozen subscription image adapter, NOT the application's production API path",
              "models": {}, "bindings": {}}
    for run in runs:
        directory = root / run
        report["bindings"][run] = {name: digest(directory / name) for name in
                                     ("results.jsonl", "scored-results.jsonl", "scoring.json")}
        rows = [json.loads(s) for s in (directory / "scored-results.jsonl").read_text().splitlines()]
        for model in dict.fromkeys(r["model"] for r in rows):
            model_rows = [r for r in rows if r["model"] == model]
            model_report = {}
            for scope, selected in (("supported_13", [r for r in model_rows if r["doc_type"] != "1040"]),
                                    ("best_effort_1040", [r for r in model_rows if r["doc_type"] == "1040"]),
                                    ("original_12_comparison", [r for r in model_rows if r["doc_type"] not in ("1099-G", "1099-K")])):
                model_report[scope] = {}
                for variant in ("clean", "degraded_scan", "both"):
                    subset = selected if variant == "both" else [r for r in selected if r["variant"] == variant]
                    fields = sum(r["score"]["expected_fields"] for r in subset)
                    correct = sum(r["score"]["correct"] for r in subset)
                    gate_pass = all(r["dedicated_prompt"] and r["classification_correct"] and
                                    r["status"] == "ok" and r["score"]["exact_document"] for r in subset)
                    model_report[scope][variant] = {
                        "documents": len(subset), "pages": sum(r["page_count"] for r in subset),
                        "correct_fields": correct, "expected_fields": fields, "field_accuracy": correct / fields,
                        "populated_correct": sum(r["score"]["populated_correct"] for r in subset),
                        "populated_fields": sum(r["score"]["populated_fields"] for r in subset),
                        "blank_correct": sum(r["score"]["blank_correct"] for r in subset),
                        "blank_fields": sum(r["score"]["blank_fields"] for r in subset),
                        "exact_documents": sum(r["score"]["exact_document"] for r in subset),
                        "classifications_correct": sum(r["classification_correct"] for r in subset),
                        "runtime_errors": sum(r["status"] != "ok" for r in subset),
                        "extraction_seconds_per_page": sum(r["extraction_seconds"] for r in subset) / sum(r["page_count"] for r in subset),
                        "release_gate_passed": gate_pass if scope == "supported_13" else None,
                        "failed_exact_documents": [{"fixture_id": r["fixture_id"],
                            "wrong_fields": [f for f in r["score"]["fields"] if not f["correct"]],
                            "extra_fields": r["score"]["extra_fields"], "shape_errors": r["score"]["shape_errors"]}
                            for r in subset if not r["score"]["exact_document"]]}
            report["models"][model] = model_report
    write_json(root / "release-views.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", required=True)
    args = parser.parse_args()
    build(Path(__file__).parent, args.runs)
