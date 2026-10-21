"""Reconcile an observed full matrix without weakening the existing strict gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fixtures import _specs
from .runner import digest, summarize, write_json


def report(root: Path, runs: list[str]) -> dict:
    manifest_path = root / "manifest.json"
    fixtures = json.loads(manifest_path.read_text())
    expected_ids = {f["fixture_id"] for f in fixtures}
    original_types = {s[0] for s in _specs()}
    models = {}
    bindings = {}
    for run in runs:
        directory = root / run
        summarize(directory)  # Refuses stale regrading receipts.
        scoring = json.loads((directory / "scoring.json").read_text())
        if scoring["manifest_sha256"] != digest(manifest_path):
            raise ValueError("Scoring manifest differs from report manifest")
        bindings[run] = {name: digest(directory / name) for name in
                         ("metadata.json", "results.jsonl", "scored-results.jsonl", "scoring.json")}
        records = [json.loads(line) for line in (directory / "scored-results.jsonl").read_text().splitlines()]
        for model in dict.fromkeys(r["model"] for r in records):
            subset = [r for r in records if r["model"] == model]
            ids = [r["fixture_id"] for r in subset]
            if len(ids) != len(set(ids)) or set(ids) != expected_ids:
                raise ValueError(f"Incomplete/duplicate matrix for {model}")
            populations = {}
            for scope, selected in (("original_12", [r for r in subset if r["doc_type"] in original_types]),
                                    ("all_14", subset)):
                populations[scope] = {}
                for variant in ("clean", "degraded_scan", "both"):
                    rows = selected if variant == "both" else [r for r in selected if r["variant"] == variant]
                    failures = [{"fixture_id": r["fixture_id"],
                                 "reasons": [label for label, ok in (
                                     ("dedicated_schema", r["dedicated_prompt"]),
                                     ("classification", r["classification_correct"]),
                                     ("runtime", r["status"] == "ok"),
                                     ("exact_document", r["score"]["exact_document"])) if not ok],
                                 "wrong_fields": [f for f in r["score"]["fields"] if not f["correct"]],
                                 "extra_fields": r["score"]["extra_fields"],
                                 "shape_errors": r["score"]["shape_errors"]}
                                for r in rows if not (r["dedicated_prompt"] and r["classification_correct"]
                                                      and r["status"] == "ok" and r["score"]["exact_document"])]
                    populations[scope][variant] = {
                        "documents": len(rows), "pages": sum(r["page_count"] for r in rows),
                        "correct_fields": sum(r["score"]["correct"] for r in rows),
                        "expected_fields": sum(r["score"]["expected_fields"] for r in rows),
                        "exact_documents": sum(r["score"]["exact_document"] for r in rows),
                        "classifications_correct": sum(r["classification_correct"] for r in rows),
                        "runtime_errors": sum(r["status"] != "ok" for r in rows),
                        "extraction_seconds_per_page": sum(r["extraction_seconds"] for r in rows) /
                                                       sum(r["page_count"] for r in rows),
                        "strict_gate_passed": not failures, "failures": failures}
            models[model] = populations
    result = {"application_revision": "533760d94d43bd7c93bf10e09e3f5f84eb55e510",
              "scope": "Synthetic extraction with separately scored classification; not end-to-end ingest or real-world accuracy",
              "strict_gate": "Dedicated schema AND correct classification AND no runtime error AND exact document; every fixture",
              "original_12_types": sorted(original_types),
              "all_types": sorted({f["doc_type"] for f in fixtures}),
              "manifest_sha256": digest(manifest_path), "bindings": bindings, "models": models}
    write_json(root / "gate-report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runs", nargs="+", required=True)
    args = parser.parse_args()
    report(args.root, args.runs)
