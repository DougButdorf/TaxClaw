"""Run synthetic documents through TaxClaw's real render/prompt/merge code.

No credentials are accepted or persisted. Claude runs through a user-provided
subscription wrapper, with image-only stdin and all tools disabled.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from .grader import score

ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def parse_json(text: str) -> dict:
    text = text.strip().lstrip("\ufeff")
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if "```" in text:
        text = text[:text.rfind("```")]
    if not text.strip().startswith(("{", "[")):
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if match:
            text = match.group(1)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("model returned non-object JSON")
    return result


def git_revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True).strip()


def claude_call(wrapper: Path, model: str, prompt: str, image: bytes,
                timeout: float, pages: list[dict]) -> dict:
    content = [{"type": "image", "source": {"type": "base64",
                "media_type": "image/png", "data": base64.b64encode(image).decode()}},
               {"type": "text", "text": prompt}]
    request = {"type": "user", "message": {"role": "user", "content": content}}
    cmd = [str(wrapper), "--print", "--model", model, "--no-session-persistence",
           "--tools", "", "--strict-mcp-config", "--setting-sources", "",
           "--disable-slash-commands", "--input-format", "stream-json",
           "--output-format", "stream-json", "--verbose"]
    started = time.perf_counter()
    page = {"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "image_sha256": hashlib.sha256(image).hexdigest()}
    pages.append(page)
    try:
        proc = subprocess.run(cmd, input=json.dumps(request) + "\n", text=True,
                              capture_output=True, timeout=timeout, cwd=ROOT)
        events = []
        for line in proc.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        results = [e for e in events if e.get("type") == "result"]
        if not results:
            raise RuntimeError(f"Claude wrapper exited {proc.returncode} without result")
        result = results[-1]
        # Only preserve bounded extraction evidence, not CLI session identifiers/settings.
        page.update({k: result.get(k) for k in
                     ("duration_ms", "duration_api_ms", "stop_reason", "is_error", "subtype")})
        page["models_used"] = sorted(result.get("modelUsage", {}))
        page["usage"] = result.get("usage")
        page["raw_text"] = result.get("result", "")
        if proc.returncode or result.get("is_error"):
            raise RuntimeError(f"Claude extraction failed: {page['raw_text'][:400]}")
        if page["models_used"] != [model]:
            raise RuntimeError(f"Requested {model}; CLI reported {page['models_used']}; no substitution accepted")
        return parse_json(page["raw_text"])
    finally:
        page["wall_seconds"] = time.perf_counter() - started


def run(args: argparse.Namespace) -> None:
    import ollama
    from src import ai, extract
    from src.classify import classify_document
    from src.config import Config

    manifest_path = args.fixtures / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    fixtures = manifest if isinstance(manifest, list) else manifest["fixtures"]
    if args.types:
        fixtures = [f for f in fixtures if f["doc_type"] in args.types]
    if not fixtures:
        raise SystemExit("No fixtures selected")
    args.output.mkdir(parents=True, exist_ok=True)
    client = ollama.Client(host=args.host, timeout=args.timeout)
    inventory = client.list().model_dump(mode="json") if args.transport != "claude-subscription" else None
    signature = {"git_revision": git_revision(), "transport": args.transport,
                 "models": args.models, "timeout_seconds": args.timeout,
                 "manifest_sha256": digest(manifest_path), "types": args.types,
                 "source_sha256": {name: digest(ROOT / name) for name in
                                    ("src/ai.py", "src/extract.py", "src/classify.py",
                                     "benchmarks/taxclaw_accuracy/runner.py",
                                     "benchmarks/taxclaw_accuracy/grader.py",
                                     "benchmarks/taxclaw_accuracy/fixtures.py")},
                 "ollama_host": args.host if inventory is not None else None,
                 "requested_model_digests": {name: sorted(m["digest"] for m in inventory["models"]
                    if (m.get("model") or m.get("name")) == name) for name in args.models}
                    if inventory is not None else None,
                 "claude_wrapper_sha256": digest(args.claude_wrapper) if args.transport == "claude-subscription" else None,
                 "python": platform.python_version(),
                 "packages": {p: importlib.metadata.version(p) for p in
                              ("pymupdf", "ollama", "anthropic", "pyyaml")},
                 "renderer_scale": 2.0,
                 "classification": "scored separately; extraction uses answer-key document type",
                 "structured_format": "json" if args.transport == "ollama-json" else None,
                 "max_tokens_override": 2048 if args.transport == "ollama-json" else None,
                 "fixture_hashes": {f["fixture_id"]: digest(args.fixtures / f["pdf_path"])
                                    for f in fixtures}}
    metadata = args.output / "metadata.json"
    if metadata.exists():
        previous = json.loads(metadata.read_text())
        if previous["signature"] != signature:
            raise SystemExit("Run provenance changed; use a new output directory")
    else:
        write_json(metadata, {"created_utc": datetime.now(timezone.utc).isoformat(),
                              "signature": signature, "ollama_inventory": inventory})
    result_file = args.output / "results.jsonl"
    completed = set()
    if result_file.exists():
        completed = {(r["model"], r["fixture_id"]) for r in
                     (json.loads(line) for line in result_file.read_text().splitlines())}

    original_image_call = extract.chat_json_from_image
    original_ollama_chat = ai.ollama.chat
    base_chat = client.chat
    for model in args.models:
        if inventory is not None:
            names = [m.get("model") or m.get("name") for m in inventory["models"]]
            if model not in names:
                raise SystemExit(f"Requested model not installed: {model}; no substitution")
        for fixture in fixtures:
            if (model, fixture["fixture_id"]) in completed:
                continue
            pages: list[dict] = []
            classification_pages: list[dict] = []
            active_pages = pages

            def recording_chat(**kwargs):
                page = {"prompt_sha256": hashlib.sha256(kwargs["messages"][0]["content"].encode()).hexdigest()}
                active_pages.append(page)
                before = time.perf_counter()
                try:
                    response = base_chat(**kwargs)
                    raw = response.model_dump(mode="json")
                    page.update({k: raw.get(k) for k in
                                 ("model", "done_reason", "total_duration", "load_duration",
                                  "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")})
                    page["raw_text"] = raw.get("message", {}).get("content", "")
                    page["thinking_tokens_text_present"] = bool(raw.get("message", {}).get("thinking"))
                    if raw.get("model") != model:
                        raise RuntimeError(f"Requested {model}; Ollama returned {raw.get('model')}; no substitution accepted")
                    return response
                finally:
                    page["wall_seconds"] = time.perf_counter() - before

            def custom_image_call(*, cfg, prompt, image_bytes):
                if args.transport == "claude-subscription":
                    return claude_call(args.claude_wrapper, model, prompt, image_bytes,
                                       args.timeout, active_pages)
                response = recording_chat(model=model,
                    messages=[{"role": "user", "content": prompt,
                               "images": [base64.b64encode(image_bytes).decode()]}],
                    options={"temperature": 0, "num_predict": 2048}, format="json")
                return parse_json(response["message"]["content"])

            ai.ollama.chat = recording_chat
            extract.chat_json_from_image = (original_image_call if args.transport == "app" else custom_image_call)
            # Classification is mostly text; use the same selected transport if vision is required.
            import src.classify as classifier
            classifier.chat_json_from_image = extract.chat_json_from_image
            cfg = Config(model_backend="local", local_model=model)
            pdf = args.fixtures / fixture["pdf_path"]
            record = {"model": model, "transport": args.transport,
                      "fixture_id": fixture["fixture_id"], "doc_type": fixture["doc_type"],
                      "page_count": fixture["page_count"], "pdf_sha256": digest(pdf),
                      "started_utc": datetime.now(timezone.utc).isoformat(),
                      "dedicated_prompt": fixture["doc_type"] in extract.PROMPTS}
            active_pages = classification_pages
            before_classify = time.perf_counter()
            try:
                classification = classify_document(str(pdf), cfg)
                record["classification"] = classification
                record["classification_correct"] = classification["doc_type"] == fixture["doc_type"]
            except Exception as exc:
                record["classification_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
                record["classification_correct"] = False
            record["classification_seconds"] = time.perf_counter() - before_classify
            record["classification_pages"] = classification_pages
            active_pages = pages
            before = time.perf_counter()
            actual = {}
            try:
                actual = extract.extract_document(str(pdf), fixture["doc_type"], cfg)
                record["status"] = "ok"
                record["actual"] = actual
            except Exception as exc:
                record["status"] = "error"
                record["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
            record["extraction_seconds"] = time.perf_counter() - before
            record["seconds_per_page"] = record["extraction_seconds"] / fixture["page_count"]
            record["pages"] = pages
            record["score"] = score(fixture["expected"], actual, fixture["field_types"])
            # HTTP/decode failures cannot earn blank-field credit from an empty response.
            if record["status"] != "ok":
                record["score"] = score(fixture["expected"], None, fixture["field_types"])
            if inventory is not None:
                try:
                    record["resident_models_after"] = client.ps().model_dump(mode="json")
                except Exception:
                    record["resident_models_after"] = None
            with result_file.open("a") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{model} {fixture['doc_type']} {record['status']}: "
                  f"{record['score']['correct']}/{record['score']['expected_fields']} fields; "
                  f"{record['seconds_per_page']:.2f}s/page", flush=True)
            ai.ollama.chat = original_ollama_chat
            extract.chat_json_from_image = original_image_call
    summarize(args.output)


def summarize(output: Path) -> dict:
    scored_path = output / "scored-results.jsonl"
    source = scored_path if scored_path.exists() else output / "results.jsonl"
    records = [json.loads(line) for line in source.read_text().splitlines()]
    if scored_path.exists():
        receipt = json.loads((output / "scoring.json").read_text())
        if receipt["raw_results_sha256"] != digest(output / "results.jsonl"):
            raise SystemExit("Raw results changed since regrading; regrade again")
    models = {}
    for name in dict.fromkeys(r["model"] for r in records):
        subset = [r for r in records if r["model"] == name]
        correct = sum(r["score"]["correct"] for r in subset)
        total = sum(r["score"]["expected_fields"] for r in subset)
        populated = sum(r["score"]["populated_fields"] for r in subset)
        models[name] = {
            "documents_finished": len(subset), "correct_fields": correct, "expected_fields": total,
            "field_accuracy": correct / total if total else 0,
            "populated_accuracy": sum(r["score"]["populated_correct"] for r in subset) / populated if populated else 0,
            "exact_documents": sum(r["score"]["exact_document"] for r in subset),
            "error_documents": sum(r["status"] != "ok" for r in subset),
            "classification_correct": sum(r["classification_correct"] for r in subset),
            "extra_field_count": sum(len(r["score"]["extra_fields"]) for r in subset),
            "wall_seconds_per_page": sum(r["extraction_seconds"] for r in subset) / sum(r["page_count"] for r in subset),
            "forms": {r["doc_type"]: {"accuracy": r["score"]["accuracy"],
                      "correct_fields": r["score"]["correct"], "expected_fields": r["score"]["expected_fields"],
                      "status": r["status"], "exact": r["score"]["exact_document"],
                      "seconds_per_page": r["seconds_per_page"]} for r in subset}}
    report = {"schema_version": 1, "scope": "synthetic clean-form smoke benchmark, not real-world accuracy",
              "grader_sha256": digest(Path(__file__).with_name("grader.py")),
              "models": models}
    write_json(output / "summary.json", report)
    return report


def regrade(args: argparse.Namespace) -> None:
    """Keep inference evidence immutable; score it again with the current grader."""
    manifest_path = args.fixtures / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    fixtures = manifest if isinstance(manifest, list) else manifest["fixtures"]
    by_id = {f["fixture_id"]: f for f in fixtures}
    raw = args.output / "results.jsonl"
    metadata = json.loads((args.output / "metadata.json").read_text())
    if metadata["signature"]["manifest_sha256"] != digest(manifest_path):
        raise SystemExit("Answer-key manifest changed; refusing regrade")
    records = [json.loads(line) for line in raw.read_text().splitlines()]
    for record in records:
        fixture = by_id[record["fixture_id"]]
        if record["pdf_sha256"] != digest(args.fixtures / fixture["pdf_path"]):
            raise SystemExit("Fixture PDF changed; refusing regrade")
        # Earlier exploratory harnesses logged response identity but did not reject it.
        identity_ok = all((p.get("model") == record["model"] if record["transport"] != "claude-subscription"
                           else p.get("models_used") == [record["model"]]) for p in record["pages"])
        if not identity_ok:
            record["status"] = "error"
            record["error"] = "Recorded provider model does not match requested model"
        actual = record.get("actual") if record["status"] == "ok" else None
        record["score"] = score(fixture["expected"], actual, fixture["field_types"])
    (args.output / "scored-results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    write_json(args.output / "scoring.json", {
        "raw_results_sha256": digest(raw), "manifest_sha256": digest(manifest_path),
        "grader_sha256": digest(Path(__file__).with_name("grader.py")),
        "regraded_utc": datetime.now(timezone.utc).isoformat(),
        "records": len(records), "model_identity_checked": True})
    summarize(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--fixtures", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--models", nargs="+", required=True)
    run_parser.add_argument("--types", nargs="+")
    run_parser.add_argument("--transport", choices=("app", "ollama-json", "claude-subscription"), default="app")
    run_parser.add_argument("--host", default="http://127.0.0.1:11434")
    run_parser.add_argument("--timeout", type=float, default=180)
    run_parser.add_argument("--claude-wrapper", type=Path)
    summary = commands.add_parser("summarize")
    summary.add_argument("--output", type=Path, required=True)
    scoring = commands.add_parser("regrade")
    scoring.add_argument("--output", type=Path, required=True)
    scoring.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        from .fixtures import build_fixtures
        build_fixtures(args.output)
    elif args.command == "summarize":
        summarize(args.output)
    elif args.command == "regrade":
        regrade(args)
    else:
        if args.transport == "claude-subscription" and not args.claude_wrapper:
            parser.error("--claude-wrapper is required for subscription mode")
        run(args)


if __name__ == "__main__":
    main()
