"""Real stdio MCP client check for `taxclaw mcp` (uses the official `mcp` SDK's ClientSession).

No-model mode (CI):   python -P tests/mcp_stdio_client.py --server /path/to/bin/taxclaw
With a model:         python -P tests/mcp_stdio_client.py --server /path/to/bin/taxclaw --ingest /abs/w2.pdf

The server inherits this process's environment (set HOME to a temp dir to
isolate config/data). Exits non-zero on any failure. Prints a short transcript.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client

EXPECTED_TOOLS = {"ingest_document", "list_documents", "get_document", "export_documents", "list_models"}


def _package_version() -> str:
    # Run with `python -P` (no repo on sys.path), so read src/__init__.py as text.
    init_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "__init__.py")
    for line in open(init_py, encoding="utf-8"):
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise AssertionError("no __version__ in src/__init__.py")


def _payload(result: Any) -> Any:
    if getattr(result, "structured_content", None) is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    try:
        return json.loads("".join(texts))
    except Exception:  # noqa: BLE001
        return "".join(texts)


async def run(server: str, ingest: str | None, expect: dict[str, str]) -> int:
    params = StdioServerParameters(command=server, args=["mcp"], env=dict(os.environ))
    log = lambda msg: print(f"[mcp-client] {msg}", flush=True)  # noqa: E731
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            log(f"initialize ok: server={init.server_info.name} {init.server_info.version} protocol={init.protocol_version}")
            want = _package_version()
            assert init.server_info.version == want, (init.server_info.version, want)

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            log(f"tools ({len(names)}): {', '.join(sorted(names))}")
            missing = EXPECTED_TOOLS - names
            assert not missing, f"missing tools: {missing}"
            for t in tools.tools:
                assert t.description and t.input_schema.get("type") == "object", t.name

            r = await session.call_tool("list_models", {})
            assert not r.is_error, r
            models = _payload(r)
            t1, t2, t3 = models["tiers"]
            log(
                f"list_models ok: backend={models['current']['model_backend']} "
                f"tier1 vision={len(t1['vision_models_installed'])} reachable={t1['ollama_reachable']} "
                f"tier2 configured={[p['provider'] for p in t2['providers'] if p['configured']]} "
                f"tier3 configured={[o['id'] for o in t3['options'] if o.get('configured')]}"
            )

            r = await session.call_tool("list_documents", {})
            assert not r.is_error, r
            docs = _payload(r)
            log(f"list_documents ok: count={docs['count']}")

            # Accountant formats are advertised and work without a model (empty DB is fine).
            export_tool = next(t for t in tools.tools if t.name == "export_documents")
            fmt_enum = export_tool.input_schema["properties"]["format"].get("enum") or []
            assert {"8949_csv", "txf"} <= set(fmt_enum), fmt_enum
            r = await session.call_tool("export_documents", {"all": True, "format": "8949_csv"})
            assert not r.is_error, r
            e8949 = _payload(r)
            assert e8949["content"].startswith("# TaxClaw Data Export") and "a_description" in e8949["content"], e8949
            assert "Not tax advice" in e8949["notice"], e8949
            r = await session.call_tool("export_documents", {"all": True, "format": "txf"})
            assert not r.is_error, r
            etxf = _payload(r)
            assert etxf["content"].startswith("V042\r\nATaxClaw") and etxf["records"] == 0, etxf
            log(f"export_documents 8949_csv/txf ok: rows={e8949['rows']} txf_records={etxf['records']}")

            # Safety: relative path and missing file are clean tool errors.
            r = await session.call_tool("ingest_document", {"path": "relative.pdf"})
            assert r.is_error, "relative path should be rejected"
            r = await session.call_tool("ingest_document", {"path": "/nonexistent/taxclaw-mcp-check.pdf"})
            assert r.is_error, "missing file should be rejected"
            log("ingest_document rejects relative and missing paths ok")

            if not ingest:
                return 0

            t0 = time.monotonic()
            r = await session.call_tool("ingest_document", {"path": ingest, "filer": "mcp-check", "tax_year": 2025}, read_timeout_seconds=900)
            dt = time.monotonic() - t0
            assert not r.is_error, _payload(r)
            ing = _payload(r)
            doc_id = ing["document_id"]
            log(
                f"ingest_document ok in {dt:.1f}s: id={doc_id} doc_type={ing['doc_type']} "
                f"needs_review={ing['needs_review']} overall_confidence={ing['overall_confidence']} method={ing.get('extraction_method')}"
            )

            r = await session.call_tool("get_document", {"document_id": doc_id})
            assert not r.is_error, r
            got = _payload(r)
            fields = {f["field_path"]: f["field_value"] for f in got["fields"]}
            log(f"get_document ok: {len(got['fields'])} fields; confidence keys present={all('confidence' in f for f in got['fields'])}")
            hits = 0
            for k, want in expect.items():
                have = fields.get(k)
                norm = lambda v: (v or "").replace(",", "").replace("$", "").strip()  # noqa: E731
                ok = norm(have) == norm(want)
                hits += ok
                log(f"  {k}: {have!r} {'==' if ok else '!='} {want!r}")
            if expect:
                log(f"field accuracy: {hits}/{len(expect)}")

            r = await session.call_tool("export_documents", {"document_id": doc_id, "format": "json"})
            assert not r.is_error, r
            exp = _payload(r)
            data = json.loads(exp["content"])
            assert data.get("id") == doc_id or doc_id in exp["content"], "export does not contain the document"
            log(f"export_documents json ok: {len(exp['content'])} chars, content_type={exp['content_type']}")
            return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="absolute path to bin/taxclaw")
    ap.add_argument("--ingest", default=None, help="absolute path of a document to ingest")
    ap.add_argument("--expect-json", default=None, help="JSON object of field_path -> expected value")
    a = ap.parse_args()
    expect = json.loads(a.expect_json) if a.expect_json else {}
    return asyncio.run(run(a.server, a.ingest, expect))


if __name__ == "__main__":
    sys.exit(main())
