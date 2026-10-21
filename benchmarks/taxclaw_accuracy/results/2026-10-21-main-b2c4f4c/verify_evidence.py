"""Offline raw-response replay and strict regrading for the fresh 26-case gate."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from benchmarks.taxclaw_accuracy.grader import score
from benchmarks.taxclaw_accuracy.runner import digest, parse_json, write_json
from src import extract
from src.config import Config


def verify(fixtures):
    root = Path(__file__).parent
    run = root / "haiku-subscription"
    freeze = json.loads((root / "freeze.json").read_text())
    signature = json.loads((run / "metadata.json").read_text())["signature"]
    manifest = json.loads((root / "manifest.json").read_text())
    selected = {f["fixture_id"]: f for f in manifest if f["doc_type"] != "1040"}
    assert len(selected) == freeze["documents"] == 26
    assert digest(root / "manifest.json") == digest(fixtures / "manifest.json") == freeze["manifest_sha256"]
    assert signature["git_revision"] == freeze["harness_revision"]
    assert signature["models"] == ["claude-haiku-5-5"]
    assert signature["transport"] == "claude-subscription"
    assert signature["timeout_seconds"] == 90
    assert signature["renderer_scale"] == 2.0
    assert signature["claude_wrapper_sha256"] == freeze["wrapper_sha256"]
    assert set(signature["types"]) == set(freeze["gate_types"])
    assert signature["variants"] is None
    for name, sha in {**freeze["source_sha256"], **freeze["harness_sha256"], **signature["source_sha256"]}.items():
        assert digest(Path(name)) == sha, name
    for name in freeze["source_sha256"]:
        assert Path(name).read_bytes() == subprocess.check_output(["git", "show", f'{freeze["application_revision"]}:{name}'])
    raw = [json.loads(s) for s in (run / "results.jsonl").read_text().splitlines()]
    graded = [json.loads(s) for s in (run / "scored-results.jsonl").read_text().splitlines()]
    assert len(raw) == len(graded) == 26
    seen = set()
    changed_years = []
    for record, rescored in zip(raw, graded):
        fid = record["fixture_id"]
        assert fid not in seen
        seen.add(fid)
        fixture = selected[fid]
        for key in ("doc_type", "variant", "page_count"):
            assert record[key] == fixture[key]
        pdf = fixtures / fixture["pdf_path"]
        assert digest(pdf) == record["pdf_sha256"] == signature["fixture_hashes"][fid]
        assert record["dedicated_prompt"] == (extract.schema_for(record["doc_type"]) is not None)
        assert record["classification_correct"] == (record.get("classification", {}).get("doc_type") == record["doc_type"])
        for page in record["pages"] + record["classification_pages"]:
            assert page["models_used"] == [record["model"]] == ["claude-haiku-5-5"]
        if record["status"] == "ok":
            assert len(record["pages"]) == fixture["page_count"]
            page_iterator = iter(record["pages"])

            def replay(*, cfg, prompt, image_bytes, schema=None):
                page = next(page_iterator)
                assert hashlib.sha256(prompt.encode()).hexdigest() == page["prompt_sha256"]
                assert hashlib.sha256(image_bytes).hexdigest() == page["image_sha256"]
                return copy.deepcopy(parse_json(page["raw_text"]))

            with patch.object(extract, "chat_json_from_image", side_effect=replay):
                result = extract.extract_document_with_meta(str(pdf), record["doc_type"], Config(model_backend="local", local_model=record["model"]))
            assert next(page_iterator, None) is None
            assert result.data == record["actual"], fid
            for index, page in enumerate(record["pages"]):
                original = parse_json(page["raw_text"])
                normalized, review = extract.apply_tax_year_contract(original, record["doc_type"])
                if original != normalized:
                    changed_years.append({"fixture_id": fid, "page": index + 1, "review_fields": review})
        expected_score = score(fixture["expected"], record.get("actual") if record["status"] == "ok" else None, fixture["field_types"])
        assert record["score"] == rescored["score"] == expected_score, fid
        assert record == rescored, fid
    assert seen == set(selected)
    scoring = json.loads((run / "scoring.json").read_text())
    assert scoring["raw_results_sha256"] == digest(run / "results.jsonl")
    assert scoring["grader_sha256"] == freeze["strict_scorer_unchanged_from_prior"]
    report = {"application_revision": freeze["application_revision"], "records_verified": len(raw),
              "raw_response_replay_through_application": True, "prompt_and_image_hashes_verified": True,
              "all_scores_independently_recomputed": True, "model_identities_verified": True,
              "year_type_normalizations_observed": changed_years,
              "bindings": {name: digest(run / name) for name in ("results.jsonl", "scored-results.jsonl", "scoring.json", "metadata.json")},
              "verifier_sha256": digest(Path(__file__))}
    write_json(root / "verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    verify(parser.parse_args().fixtures)
