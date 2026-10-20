from __future__ import annotations

# CLI implementation imported by bin/taxclaw and bin/tax-extract.

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import load_config
from .db import init_db
from .exporter import (
    export_all_csv_long,
    export_all_csv_wide,
    export_all_json,
    export_doc_csv_long,
    export_doc_csv_wide,
    export_doc_json,
)
from .store import list_documents


def _err(msg: str) -> None:
    print(f"taxclaw: {msg}", file=sys.stderr)


def _print_json(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")


def cmd_ingest(args: argparse.Namespace) -> int:
    from .pipeline import IngestError, ingest_path

    cfg = load_config()
    try:
        result = ingest_path(args.path, cfg, filer=args.filer, tax_year=args.year)
    except IngestError as e:
        next_step = None
        if e.stage == "backend":
            from .doctor import backend_next_step

            next_step = backend_next_step(cfg)
        if args.json:
            out = {"ok": False, "stage": e.stage, "error": str(e), "document_id": e.document_id}
            if next_step:
                out["next_step"] = next_step
            _print_json(out)
        else:
            if e.document_id:
                print(e.document_id)
            _err(str(e))
            if next_step:
                _err(f"next step: {next_step}")
        return e.exit_code

    if args.json:
        _print_json({"ok": True, **result})
    else:
        print(result["document_id"])
    return 0


_LIST_KEYS = (
    "id", "doc_type", "tax_year", "filer", "status", "needs_review", "overall_confidence",
    "classification_confidence", "original_filename", "display_name", "created_at", "notes",
)


def _list_entry(d: dict[str, Any]) -> dict[str, Any]:
    from .provenance import parse_processed_by

    out = {k: d.get(k) for k in _LIST_KEYS}
    out["processed_by"] = parse_processed_by(d.get("processed_by"))
    return out


def cmd_list(args: argparse.Namespace) -> int:
    init_db()
    docs = list_documents(filer=args.filer, year=args.year, doc_type=args.type, needs_review=args.needs_review)
    if args.json:
        _print_json({"documents": [_list_entry(d) for d in docs], "count": len(docs)})
        return 0
    for d in docs:
        print(
            f"{d['id']}\t{d.get('doc_type')}\t{d.get('tax_year')}\t{d.get('filer')}\tneeds_review={d.get('needs_review')}\t{d.get('status')}"
        )
    return 0


def _export_accountant(args: argparse.Namespace) -> int:
    """Form 8949 CSV / TXF: content on stdout, notice and warnings on stderr."""

    from .accountant_exports import NOTICE_TEXT, build_8949, export_txf

    doc_ids = None if args.all else list(dict.fromkeys(args.id))
    try:
        if args.format == "8949":
            res = build_8949(doc_ids)
            sys.stdout.write(res.content)
            summary = f"{res.rows} row(s), {res.needs_review} need review"
        else:
            res = export_txf(doc_ids)
            sys.stdout.flush()
            sys.stdout.buffer.write(res.content.encode("ascii"))  # keep the spec's CR+LF as-is
            sys.stdout.buffer.flush()
            summary = f"{res.records} TXF record(s)"
    except ValueError as e:
        _err(str(e))
        return 2
    _err(f"{args.format}: {summary}. {NOTICE_TEXT}")
    _err(res.processed_by_line)
    for w in res.warnings:
        _err(f"warning: {w}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    init_db()

    if not args.all and not args.id:
        raise SystemExit("--id required unless --all")
    if args.format in ("8949", "txf"):
        return _export_accountant(args)
    if args.id and len(args.id) > 1:
        raise SystemExit(f"--format {args.format} takes one --id (or --all)")
    if args.id:
        args.id = args.id[0]

    if args.all:
        if args.format == "wide":
            sys.stdout.write(export_all_csv_wide())
            return 0
        if args.format == "long":
            sys.stdout.write(export_all_csv_long())
            return 0
        if args.format == "json":
            sys.stdout.write(export_all_json())
            return 0
        raise SystemExit("unknown format")

    if args.format == "wide":
        sys.stdout.write(export_doc_csv_wide(args.id))
        return 0
    if args.format == "long":
        sys.stdout.write(export_doc_csv_long(args.id))
        return 0
    if args.format == "json":
        sys.stdout.write(export_doc_json(args.id))
        return 0

    raise SystemExit("unknown format")


def cmd_models(args: argparse.Namespace) -> int:
    from .models import build_report, format_report

    cfg = load_config()
    report = build_report(cfg, live=not args.offline)
    if args.json:
        _print_json(report)
    else:
        sys.stdout.write(format_report(report, short=args.short))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import build_report, format_report

    report = build_report(load_config(create_dirs=False))
    if args.json:
        _print_json(report)
    else:
        sys.stdout.write(format_report(report))
    return 0  # a report, not a test: "not ready" is information, not a failure


def cmd_use_cloud(args: argparse.Namespace) -> int:
    from .config import CONFIG_PATH, save_config
    from .doctor import cloud_choice, privacy_text, switch_to_cloud

    try:
        name, _backend, _preset = cloud_choice(args.backend)
    except ValueError as e:
        _err(str(e))
        return 2

    cfg = load_config()
    if not args.accept_privacy:
        retry = f"taxclaw use-cloud {name}" + (f" --model {args.model}" if args.model else "") + " --accept-privacy"
        text = privacy_text(name, args.model)
        msg = "Refused: nothing was changed. Cloud needs your explicit consent. If you accept the notice above, run: " + retry
        if args.json:
            _print_json({"ok": False, "changed": False, "error": msg, "privacy_text": text, "retry_command": retry})
        else:
            print(text)
            print()
            _err(msg)
        return 2

    try:
        switch_to_cloud(cfg, name, args.model)
    except ValueError as e:
        _err(str(e))
        if args.json:
            _print_json({"ok": False, "changed": False, "error": str(e)})
        return 2
    save_config(cfg=cfg)

    warn = None
    try:
        from .ai import ensure_backend_ready

        ensure_backend_ready(cfg)
    except Exception as e:  # noqa: BLE001
        warn = f"saved, but not ready yet: {e}"
    if args.json:
        out = {
            "ok": True,
            "changed": True,
            "model_backend": cfg.backend,
            "model": cfg.model_name(),
            "provider": cfg.cloud_provider,
            "privacy_acknowledged": True,
            "privacy_acknowledged_at": cfg.privacy_acknowledged_at,
            "documents_left_machine": True,
            "config_path": str(CONFIG_PATH),
        }
        if warn:
            out["warning"] = warn
        _print_json(out)
    else:
        print(f"Switched to cloud: {cfg.cloud_provider} / {cfg.model_name()}.")
        print(f"Consent recorded {cfg.privacy_acknowledged_at} in {CONFIG_PATH}.")
        print(f"Documents you ingest from now on are sent to {cfg.cloud_provider}. Go back any time: taxclaw use-local")
        if warn:
            _err(f"warning: {warn}")
    return 0


def cmd_use_local(args: argparse.Namespace) -> int:
    from .config import CONFIG_PATH, save_config
    from .doctor import local_status, switch_to_local

    cfg = load_config()
    was_cloud = cfg.is_cloud
    switch_to_local(cfg, args.model)
    save_config(cfg=cfg)
    status = local_status(cfg)
    if args.json:
        _print_json(
            {
                "ok": True,
                "changed": True,
                "model_backend": "local",
                "model": cfg.local_model,
                "documents_left_machine": False,
                "was_cloud": was_cloud,
                "local_ready": status["ready"],
                "next_step": status["next_step"],
                "config_path": str(CONFIG_PATH),
            }
        )
        return 0
    print(f"Switched to local: {cfg.local_model} via Ollama. Documents stay on this machine.")
    if was_cloud:
        print("Cloud consent cleared.")
    if not status["ready"]:
        _err(f"local is not ready yet: {status['next_step']}")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import main as mcp_main

    mcp_main()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    cfg = load_config()
    init_db()

    # run from skill root so templates/static resolve
    skill_dir = Path(__file__).resolve().parents[1]
    os.chdir(str(skill_dir))

    uvicorn.run("src.main:app", host="127.0.0.1", port=cfg.port, reload=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="taxclaw", description="Turn tax documents into structured data (local-first).")
    sp = p.add_subparsers(dest="cmd", required=True)

    p_ing = sp.add_parser("ingest", help="ingest + classify + extract")
    p_ing.add_argument("path")
    p_ing.add_argument("--filer", default=None)
    p_ing.add_argument("--year", type=int, default=None)
    p_ing.add_argument("--json", action="store_true", help="print a JSON result (document_id, doc_type, needs_review, ...)")
    p_ing.set_defaults(func=cmd_ingest)

    p_ls = sp.add_parser("list", help="list documents")
    p_ls.add_argument("--filer", default=None)
    p_ls.add_argument("--year", type=int, default=None)
    p_ls.add_argument("--type", default=None)
    p_ls.add_argument("--needs-review", type=int, choices=[0, 1], default=None)
    p_ls.add_argument("--json", action="store_true", help="print JSON")
    p_ls.set_defaults(func=cmd_list)

    p_ex = sp.add_parser(
        "export",
        help="export wide/long CSV, JSON, Form 8949 CSV or TXF",
        description=(
            "Export extracted data. wide/long/json export any document. 8949 (Form 8949-ready CSV, one row per "
            "sale) and txf (TXF v042 for TurboTax Desktop-style import) cover 1099-B, consolidated 1099 and "
            "1099-DA sales; their notice and warnings go to stderr. AI-extracted data: verify before use; "
            "not tax advice."
        ),
    )
    p_ex.add_argument("--id", action="append", default=None, help="document id (repeatable for --format 8949/txf)")
    p_ex.add_argument("--all", action="store_true")
    p_ex.add_argument("--format", choices=["wide", "long", "json", "8949", "txf"], default="wide")
    p_ex.set_defaults(func=cmd_export)

    p_md = sp.add_parser("models", help="show model choices: local, configured cloud, strongest with setup")
    p_md.add_argument("--json", action="store_true", help="print JSON")
    p_md.add_argument("--offline", action="store_true", help="skip live provider model lists (no network)")
    p_md.add_argument("--short", action="store_true", help="short summary")
    p_md.set_defaults(func=cmd_models)

    p_doc = sp.add_parser(
        "doctor",
        aliases=["setup"],
        help="first-run check: local status, cloud with your own keys, hosted (read-only)",
        description=(
            "Read-only checks and three explicit paths: (1) local Ollama on this machine, (2) cloud with your own "
            "keys, (3) TaxClaw Cloud (hosted, coming soon). Installs and downloads nothing, writes nothing, and "
            "never switches to cloud."
        ),
    )
    p_doc.add_argument("--json", action="store_true", help="print the report as JSON (for agents)")
    p_doc.set_defaults(func=cmd_doctor)

    p_uc = sp.add_parser(
        "use-cloud",
        help="switch to a cloud provider (needs --accept-privacy; records your consent)",
        description=(
            "Switch extraction to a cloud provider. Without --accept-privacy this prints the privacy text and "
            "refuses. With it, writes model_backend, the model, privacy_acknowledged, privacy_acknowledged_at and "
            "the provider name to config."
        ),
    )
    p_uc.add_argument("backend", help="anthropic | openai | gemini | openrouter | cloudflare_clairic")
    p_uc.add_argument("--model", default=None, help="vision-capable model id (default: the catalog's pick where one is confirmed)")
    p_uc.add_argument("--accept-privacy", action="store_true", help="I understand my documents are sent to this provider")
    p_uc.add_argument("--json", action="store_true", help="print JSON")
    p_uc.set_defaults(func=cmd_use_cloud)

    p_ul = sp.add_parser("use-local", help="switch back to local Ollama (no consent needed)")
    p_ul.add_argument("--model", default=None, help="local vision model, e.g. gemma3:4b")
    p_ul.add_argument("--json", action="store_true", help="print JSON")
    p_ul.set_defaults(func=cmd_use_local)

    p_mcp = sp.add_parser("mcp", help="run the local MCP server over stdio")
    p_mcp.set_defaults(func=cmd_mcp)

    p_sv = sp.add_parser("serve", help="run web ui")
    p_sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return int(args.func(args))
