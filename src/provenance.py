"""``processed_by``: where a document was read, recorded when the document is created.

Every extraction result carries ``{"backend", "model", "provider", "documents_left_machine"}``
so the user (and an agent) can always see whether a document went to a cloud provider.
``documents_left_machine`` is true for every non-local backend and false for local Ollama.

Documents stored before this was recorded have no block; exports report them as
"unknown" rather than guessing.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from .config import Config


def processed_by_for(cfg: Config) -> dict[str, Any]:
    return {
        "backend": cfg.backend,
        "model": cfg.model_name(),
        "provider": cfg.provider_name(),
        "documents_left_machine": bool(cfg.is_cloud),
    }


def parse_processed_by(raw: Any) -> dict[str, Any] | None:
    """Stored JSON text (or an already-parsed dict) -> dict, else None (legacy rows)."""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
        except ValueError:
            return None
        return val if isinstance(val, dict) else None
    return None


def _label(rec: dict[str, Any]) -> str:
    return f"{rec.get('backend')} / {rec.get('model') or 'no model set'} ({rec.get('provider')})"


def aggregate(records: Iterable[Any]) -> dict[str, Any]:
    """Combine per-document records into one ``processed_by`` block for an export.

    One backend and model for every document -> that block. Otherwise ``backend``/``model``
    are ``"mixed"`` and ``breakdown`` lists each combination with a document count.
    ``documents_left_machine`` is true if any document went to a cloud provider; null
    only when none did but some documents have no record.
    """

    parsed = [parse_processed_by(r) for r in records]
    known = [r for r in parsed if r]
    unknown = len(parsed) - len(known)
    if not parsed:
        return {"backend": None, "model": None, "provider": None, "documents_left_machine": False, "documents": 0}

    combos: dict[tuple, dict[str, Any]] = {}
    for r in known:
        key = (r.get("backend"), r.get("model"), r.get("provider"), bool(r.get("documents_left_machine")))
        combos.setdefault(key, {"backend": key[0], "model": key[1], "provider": key[2], "documents_left_machine": key[3], "documents": 0})
        combos[key]["documents"] += 1

    if any(c["documents_left_machine"] for c in combos.values()):
        left: bool | None = True
    else:
        left = None if unknown else False

    if len(combos) == 1 and not unknown:
        only = next(iter(combos.values()))
        return {**only, "documents_left_machine": left, "documents": len(parsed)}
    out: dict[str, Any] = {
        "backend": "mixed", "model": "mixed", "provider": "mixed",
        "documents_left_machine": left, "documents": len(parsed),
        "breakdown": list(combos.values()),
    }
    if unknown:
        out["documents_without_record"] = unknown
    return out


def notice_line(block: dict[str, Any]) -> str:
    """One human-readable line for export notices."""

    left = block.get("documents_left_machine")
    left_s = {True: "yes", False: "no", None: "unknown"}[left if left in (True, False) else None]
    if not block.get("documents"):
        return "Processed by: no documents. Documents left this machine: no."
    if block.get("backend") == "mixed":
        parts = [f"{_label(c)} x{c['documents']}" for c in block.get("breakdown", [])]
        if block.get("documents_without_record"):
            parts.append(f"{block['documents_without_record']} document(s) stored before TaxClaw recorded this")
        return f"Processed by: mixed ({'; '.join(parts)}). Documents left this machine: {left_s}."
    return f"Processed by: {_label(block)}. Documents left this machine: {left_s}."


def processed_by_for_documents(doc_ids: Iterable[str] | None = None) -> dict[str, Any]:
    """Aggregate block for stored documents (all of them when ``doc_ids`` is None)."""

    from .db import db

    with db() as con:
        if doc_ids is None:
            rows = con.execute("SELECT processed_by FROM documents").fetchall()
        else:
            ids = list(dict.fromkeys(doc_ids))
            if not ids:
                return aggregate([])
            marks = ",".join("?" * len(ids))
            rows = con.execute(f"SELECT processed_by FROM documents WHERE id IN ({marks})", ids).fetchall()
    return aggregate(r[0] for r in rows)
