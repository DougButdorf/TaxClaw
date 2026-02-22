from __future__ import annotations

import base64
import json
from typing import Any

from anthropic import Anthropic
import ollama

from .config import Config


def _b64_png(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def chat_json_from_image(*, cfg: Config, prompt: str, image_bytes: bytes) -> dict[str, Any]:
    """Send an image + prompt and require JSON-only output.

    Returns parsed JSON dict; raises on parse error.
    """

    if cfg.model_backend == "cloud":
        if not cfg.cloud_api_key:
            raise RuntimeError("cloud_api_key missing (set in config or ANTHROPIC_API_KEY)")
        client = Anthropic(api_key=cfg.cloud_api_key)
        msg = client.messages.create(
            model=cfg.cloud_model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": _b64_png(image_bytes),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text = "".join([c.text for c in msg.content if getattr(c, "type", None) == "text"])
    else:
        # Ollama multimodal: model must support images.
        b64 = _b64_png(image_bytes)
        resp = ollama.chat(
            model=cfg.local_model,
            messages=[{"role": "user", "content": prompt, "images": [b64]}],
            options={"temperature": 0},
        )
        text = resp["message"]["content"]

    text = text.strip()
    # Best-effort strip of code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    return json.loads(text)
