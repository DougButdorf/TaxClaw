"""Independent evidence reconciliation; run from repository root with --runs."""
import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.taxclaw_accuracy.grader import score, flatten
from benchmarks.taxclaw_accuracy.runner import digest, parse_json, write_json
from src import extract


def verify(root, fixtures, runs):
    freeze = json.loads((root / "freeze.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    by_id = {f["fixture_id"]: f for f in manifest}
    assert len(by_id) == len(manifest) == 28
    assert digest(root / "manifest.json") == digest(fixtures / "manifest.json") == freeze["manifest_sha256"]
    checks = {}
    for run in runs:
        directory = root / run
        metadata = json.loads((directory / "metadata.json").read_text())
        signature = metadata["signature"]
        assert signature["git_revision"] == freeze["harness_revision"]
        assert signature["manifest_sha256"] == freeze["manifest_sha256"]
        assert signature["renderer_scale"] == 2.0
        assert signature["types"] is None and signature["variants"] is None
        for name, sha in signature["source_sha256"].items():
            assert digest(Path(name)) == sha, name
        for name, sha in freeze["harness_sha256"].items():
            assert digest(Path(name)) == sha, name
        if signature["transport"] == "claude-subscription":
            assert signature["models"] == ["claude-haiku-5-5"]
            assert signature["timeout_seconds"] == 90
            assert signature["claude_wrapper_sha256"] == "a47bc8ebb817bc01318aea24aeea46220d441f160e634c7d070d1f363dceb622"
        else:
            assert signature["transport"] == "app"
            assert signature["models"] == ["gemma3:12b", "gemma3:4b"]
            assert signature["timeout_seconds"] == 180
            assert all(signature["requested_model_digests"].values())
        rows = [json.loads(s) for s in (directory / "results.jsonl").read_text().splitlines()]
        scored = [json.loads(s) for s in (directory / "scored-results.jsonl").read_text().splitlines()]
        assert len(rows) == len(scored) == 28 * len(signature["models"])
        seen = set()
        for raw, graded in zip(rows, scored):
            key = (raw["model"], raw["fixture_id"])
            assert key not in seen
            seen.add(key)
            fixture = by_id[raw["fixture_id"]]
            for name in ("doc_type", "variant", "page_count"):
                assert raw[name] == fixture[name]
            sha = digest(fixtures / fixture["pdf_path"])
            assert raw["pdf_sha256"] == signature["fixture_hashes"][raw["fixture_id"]] == sha
            assert raw["dedicated_prompt"] == (extract.schema_for(raw["doc_type"]) is not None)
            assert raw["classification_correct"] == (raw.get("classification", {}).get("doc_type") == raw["doc_type"])
            if raw["status"] == "ok":
                assert len(raw["pages"]) == fixture["page_count"]
                outputs = []
                for page in raw["pages"]:
                    if signature["transport"] == "claude-subscription":
                        assert page["models_used"] == [raw["model"]]
                    else:
                        assert page["model"] == raw["model"]
                    outputs.append(extract.clean_null_strings(parse_json(page["raw_text"])))
                if raw["doc_type"] == "1099-DA":
                    txns = [t for page in outputs for t in page.get("transactions", [])]
                    reconstructed = {"header": outputs[0].get("header") or {}, "transactions": txns,
                                     "is_multi_transaction": len(txns) > 1}
                else:
                    reconstructed = {}
                    for page in outputs:
                        reconstructed = extract._merge_page_dicts(reconstructed, page)
                    if raw["doc_type"] == "K-1":
                        reconstructed = extract.normalize_k1(reconstructed)
                assert reconstructed == raw["actual"], key
            rescored = score(fixture["expected"], raw.get("actual") if raw["status"] == "ok" else None,
                             fixture["field_types"])
            assert rescored == raw["score"] == graded["score"], key
            assert raw == graded, key
        assert seen == {(model, fixture_id) for model in signature["models"] for fixture_id in by_id}
        receipt = json.loads((directory / "scoring.json").read_text())
        assert receipt["raw_results_sha256"] == digest(directory / "results.jsonl")
        assert receipt["grader_sha256"] == freeze["strict_scorer_unchanged_from_prior"]
        checks[run] = {"records_verified": len(rows), "raw_sha256": digest(directory / "results.jsonl"),
                       "scored_sha256": digest(directory / "scored-results.jsonl"),
                       "raw_page_outputs_reconstructed": True, "all_scores_independently_recomputed": True}
    gate = json.loads((root / "gate-report.json").read_text())
    for model, population in gate["models"].items():
        assert population["original_12"]["both"]["documents"] == 24
        assert population["original_12"]["both"]["expected_fields"] == sum(len(flatten(f["expected"])) for f in manifest if f["doc_type"] not in ("1099-G", "1099-K"))
        assert population["all_14"]["both"]["documents"] == 28
        assert population["all_14"]["both"]["expected_fields"] == sum(len(flatten(f["expected"])) for f in manifest)
    release = json.loads((root / "release-views.json").read_text())
    for model, populations in release["models"].items():
        assert populations["supported_13"]["both"]["documents"] == 26
        assert populations["supported_13"]["both"]["expected_fields"] == 562
        assert populations["best_effort_1040"]["both"]["documents"] == 2
        assert populations["best_effort_1040"]["both"]["expected_fields"] == 38
        assert populations["original_12_comparison"]["both"]["documents"] == 24
    write_json(root / "parent-verification.json", {"runs": checks, "gate_report_sha256": digest(root / "gate-report.json"),
               "release_views_sha256": digest(root / "release-views.json"),
               "verifier_sha256": digest(Path(__file__)), "manifest_bound_rows": True})
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--runs", nargs="+", required=True)
    args = parser.parse_args()
    verify(Path(__file__).parent, args.fixtures, args.runs)
