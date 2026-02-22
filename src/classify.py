from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF

from .ai import chat_json_from_image
from .config import Config


@dataclass
class Classification:
    doc_type: str
    confidence: float
    method: str  # text|vision


TEXT_SIGNALS: list[tuple[str, str]] = [
    ("1099-DA", "1099-DA"),
    ("OMB No. 1545-2298", "1099-DA"),
    ("W-2 Wage", "W-2"),
    ("Wage and Tax Statement", "W-2"),
    ("OMB No. 1545-0008", "W-2"),
    ("1099-NEC", "1099-NEC"),
    ("OMB No. 1545-0116", "1099-NEC"),
    ("1099-INT", "1099-INT"),
    ("OMB No. 1545-0112", "1099-INT"),
    ("1099-DIV", "1099-DIV"),
    ("OMB No. 1545-0110", "1099-DIV"),
    ("1099-R", "1099-R"),
    ("OMB No. 1545-0119", "1099-R"),
    ("1099-B", "1099-B"),
    ("OMB No. 1545-0715", "1099-B"),
    ("Schedule K-1", "K-1"),
    ("Form 1040", "1040"),
]


CLASSIFY_PROMPT = """You are classifying a US tax document from an image of page 1.
Return JSON only.

Return:
{
  "doc_type": string,   // one of: "W-2", "1099-DA", "1099-NEC", "1099-INT", "1099-DIV", "1099-R", "1099-B", "K-1", "1040", "consolidated-1099", "unknown"
  "confidence": number, // 0 to 1
  "method": "vision"
}

Rules:
- Use "consolidated-1099" if you see evidence multiple 1099 types are included in the same statement.
- If unsure, return doc_type "unknown" with confidence <= 0.5.
"""


def classify_document(file_path: str, cfg: Config) -> dict[str, Any]:
    doc = fitz.open(file_path)
    try:
        text_parts: list[str] = []
        # first 2 pages is enough for most forms
        for i in range(min(2, doc.page_count)):
            text_parts.append(doc[i].get_text("text") or "")
        text = "\n".join(text_parts)

        hits: list[str] = []
        for needle, dtype in TEXT_SIGNALS:
            if needle.lower() in text.lower():
                hits.append(dtype)

        if hits:
            # crude confidence: single clear hit => 0.9; multiple types => consolidated
            uniq = sorted(set(hits))
            if len(uniq) >= 2 and any(t.startswith("1099-") for t in uniq):
                return {"doc_type": "consolidated-1099", "confidence": 0.85, "method": "text"}
            return {"doc_type": uniq[0], "confidence": 0.9, "method": "text"}

        # Vision fallback
        page = doc[0]
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img = pix.tobytes("png")
        out = chat_json_from_image(cfg=cfg, prompt=CLASSIFY_PROMPT, image_bytes=img)
        out.setdefault("method", "vision")
        out.setdefault("confidence", 0.5)
        out.setdefault("doc_type", "unknown")
        return out
    finally:
        doc.close()
