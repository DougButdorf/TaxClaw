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
        if args.json:
            _print_json({"ok": False, "stage": e.stage, "error": str(e), "document_id": e.document_id})
        else:
            if e.document_id:
                print(e.document_id)
            _err(str(e))
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


def cmd_list(args: argparse.Namespace) -> int:
    init_db()
    docs = list_documents(filer=args.filer, year=args.year, doc_type=args.type, needs_review=args.needs_review)
    if args.json:
        _print_json({"documents": [{k: d.get(k) for k in _LIST_KEYS} for d in docs], "count": len(docs)})
        return 0
    for d in docs:
        print(
            f"{d['id']}\t{d.get('doc_type')}\t{d.get('tax_year')}\t{d.get('filer')}\tneeds_review={d.get('needs_review')}\t{d.get('status')}"
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    init_db()

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

    if not args.id:
        raise SystemExit("--id required unless --all")

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

    p_ex = sp.add_parser("export", help="export wide/long CSV or JSON")
    p_ex.add_argument("--id", default=None)
    p_ex.add_argument("--all", action="store_true")
    p_ex.add_argument("--format", choices=["wide", "long", "json"], default="wide")
    p_ex.set_defaults(func=cmd_export)

    p_md = sp.add_parser("models", help="show model choices: local, configured cloud, strongest with setup")
    p_md.add_argument("--json", action="store_true", help="print JSON")
    p_md.add_argument("--offline", action="store_true", help="skip live provider model lists (no network)")
    p_md.add_argument("--short", action="store_true", help="short summary")
    p_md.set_defaults(func=cmd_models)

    p_mcp = sp.add_parser("mcp", help="run the local MCP server over stdio")
    p_mcp.set_defaults(func=cmd_mcp)

    p_sv = sp.add_parser("serve", help="run web ui")
    p_sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return int(args.func(args))
