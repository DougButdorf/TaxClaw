"""Full release-gate corpus, without changing either historical corpus.

The original twelve types remain represented; corrected WP-F specifications
replace 1099-R/K-1 and add 1099-G/K. Each type has a clean/image-only scan pair:
28 documents, 32 pages. No inference runs here. Byte determinism is dependency-
version-local. Run with ``python -m benchmarks.taxclaw_accuracy.full_fixtures DIR``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import __version__ as pillow_version

from . import fixtures, followup_fixtures

CORPUS_ID = "full_release_gate_v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_fixtures(output_dir: Path) -> list[dict[str, Any]]:
    """Write a flat manifest and PDFs; intermediate sources stay inside DIR.

    Unchanged clean PDFs are byte-identical to the original builder. The four
    corrected types reuse the followup builder's clean and scan PDFs verbatim.
    Expected values and leaf types are copied from those builders, never inferred.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = {
        name: _sha256(Path(module.__file__).read_bytes())
        for name, module in (("fixtures.py", fixtures), ("followup_fixtures.py", followup_fixtures))
    }
    records = []
    with tempfile.TemporaryDirectory(prefix=".full-gate-sources-", dir=output_dir) as temporary:
        sources = Path(temporary)
        original_dir, followup_dir = sources / "original", sources / "followup"
        original = fixtures.build_fixtures(original_dir)
        followup = followup_fixtures.build_fixtures(followup_dir)
        changed = {record["doc_type"] for record in followup}
        types = [record["doc_type"] for record in original]
        types.extend(dict.fromkeys(record["doc_type"] for record in followup if record["doc_type"] not in types))
        for typ in types:
            if typ in changed:
                pairs = [(record, followup_dir, "followup_fixtures.py")
                         for record in followup if record["doc_type"] == typ]
            else:
                source = next(record for record in original if record["doc_type"] == typ)
                scan = copy.deepcopy(source)
                scan["variant"] = "degraded_scan"
                pairs = [(source, original_dir, "fixtures.py"), (scan, original_dir, "fixtures.py")]
            for source, directory, module in pairs:
                source_pdf = (directory / source["pdf_path"]).read_bytes()
                generated_scan = module == "fixtures.py" and source["variant"] == "degraded_scan"
                if generated_scan:
                    with fitz.open(stream=source_pdf, filetype="pdf") as clean:
                        pdf = followup_fixtures._scan(clean, typ)
                else:
                    pdf = source_pdf
                record = copy.deepcopy(source)
                fixture_id = "full_gate_" + typ.lower().replace("-", "_") + "_" + source["variant"]
                record.update(corpus_id=CORPUS_ID, fixture_id=fixture_id, pdf_path=fixture_id + ".pdf")
                record["generation"] = {
                    "pymupdf_version": fitz.VersionBind,
                    "pillow_version": pillow_version,
                    "scan_parameters": copy.deepcopy(followup_fixtures.SCAN_PARAMETERS)
                    if source["variant"] == "degraded_scan" else None,
                    "source_module": module,
                    "source_module_sha256": source_hashes[module],
                    "scan_module_sha256": source_hashes["followup_fixtures.py"]
                    if source["variant"] == "degraded_scan" else None,
                    "source_fixture_id": source["fixture_id"],
                    "source_pdf_sha256": _sha256(source_pdf),
                    "pdf_sha256": _sha256(pdf),
                    "method": "followup._scan(original_clean)" if generated_scan else "verbatim_source_pdf",
                }
                (output_dir / record["pdf_path"]).write_bytes(pdf)
                records.append(record)
    (output_dir / "manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m benchmarks.taxclaw_accuracy.full_fixtures OUTPUT_DIR")
    build_fixtures(Path(sys.argv[1]))
