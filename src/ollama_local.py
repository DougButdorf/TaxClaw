"""Helpers for the local (Ollama) backend: host resolution, reachability,
vision-capability detection, and friendly error messages.

Ollama's own Python client already honours ``OLLAMA_HOST``; these helpers use
the same variable so error messages name the host that was actually tried.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import httpx
import ollama

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"

# Fallback only: used when an older Ollama's /api/show response has no
# "capabilities" list. Current Ollama reports capabilities directly.
_VISION_FAMILIES = frozenset({"clip", "glmocr", "qwen2vl", "qwen25vl", "internvl", "mllama"})

_RUNNER_DIGEST_ALIAS = re.compile(r"^[a-z0-9_-]+:[0-9a-f]{64}$")


class LocalModelError(RuntimeError):
    """Raised when the local Ollama backend cannot run an extraction."""


def ollama_host() -> str:
    """Return the Ollama base URL, respecting OLLAMA_HOST (same rules as the ollama client)."""

    raw = (os.environ.get("OLLAMA_HOST") or "").strip()
    if not raw:
        return DEFAULT_OLLAMA_HOST
    if "://" not in raw:
        raw = f"http://{raw}"
    parts = urlsplit(raw)
    scheme = parts.scheme or "http"
    host = parts.hostname or "127.0.0.1"
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if scheme == "https" else 11434
    path = parts.path.rstrip("/")
    return f"{scheme}://{host}:{port}{path}"


def unreachable_message(host: str | None = None) -> str:
    host = host or ollama_host()
    return (
        f"Ollama is not reachable at {host}. Start it with `ollama serve` (or open the Ollama app), "
        "check OLLAMA_HOST if Ollama runs elsewhere, or switch TaxClaw to cloud mode in Settings."
    )


def is_connection_error(exc: BaseException) -> bool:
    """True for the errors the ollama client / httpx raise when the server is down."""

    if isinstance(exc, (ConnectionError, httpx.TransportError)):
        return True
    text = str(exc)
    return "Connection refused" in text or "Failed to connect to Ollama" in text


def client(*, timeout: float | None = None) -> ollama.Client:
    return ollama.Client(host=ollama_host(), timeout=timeout)


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def vision_from_show(show: Any, families: list[str] | None = None) -> bool:
    """Decide whether a model accepts images from an /api/show response.

    Primary signal: ``capabilities`` containing "vision" (Ollama >= 0.6) together
    with "completion" (excludes image-embedding models). Fallback (older Ollama with no capabilities list): projector info,
    vision tensors in model_info, or a known vision family.
    """

    caps = _field(show, "capabilities")
    if caps:
        caps_s = {str(c) for c in caps}
        return "vision" in caps_s and "completion" in caps_s

    if _field(show, "projector_info"):
        return True
    model_info = _field(show, "modelinfo") or _field(show, "model_info") or {}
    if isinstance(model_info, dict) and any(".vision." in str(k) for k in model_info):
        return True

    if families is None:
        details = _field(show, "details")
        families = list(_field(details, "families") or []) if details is not None else []
    return any(f in _VISION_FAMILIES for f in families or [])


@lru_cache(maxsize=64)
def _check_model_cached(host: str, model: str) -> None:
    try:
        show = ollama.Client(host=host, timeout=10).show(model)
    except ollama.ResponseError as e:
        if getattr(e, "status_code", None) == 404:
            raise LocalModelError(
                f"Local model '{model}' is not installed in Ollama at {host}. "
                f"Run `ollama pull {model}` or pick an installed vision model in Settings "
                "(recommended: gemma3:4b)."
            ) from None
        raise LocalModelError(f"Ollama at {host} returned an error for model '{model}': {e}") from None
    except Exception as e:  # noqa: BLE001
        if is_connection_error(e):
            raise LocalModelError(unreachable_message(host)) from None
        raise

    if not vision_from_show(show):
        raise LocalModelError(
            f"Local model '{model}' cannot read images (Ollama does not report it as a vision chat model), "
            "so it cannot extract tax documents. Set `local_model` to a vision model in "
            "~/.config/taxclaw/config.yaml or Settings, e.g. `ollama pull gemma3:4b` then "
            "`local_model: gemma3:4b`."
        )


def ensure_vision_model(model: str) -> None:
    """Fail fast unless Ollama is reachable and ``model`` is installed with vision.

    Successful checks are cached per (host, model) for the life of the process.
    """

    _check_model_cached(ollama_host(), model)


def probe_models(*, timeout: float = 1.5) -> list[dict[str, Any]] | None:
    """Installed models as ``[{"name", "vision"}]`` (vision models first), or None if the server is unreachable.

    Unlike :func:`list_models_with_vision`, an empty list means "reachable, nothing installed".
    """

    try:
        c = client(timeout=timeout)
        listed = c.list()
    except Exception:  # noqa: BLE001
        return None

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _field(listed, "models") or []:
        name = _field(m, "model") or _field(m, "name")
        if not isinstance(name, str) or not name or name in seen:
            continue
        if _RUNNER_DIGEST_ALIAS.match(name):
            # Ollama 0.40+ also lists runner-internal digest aliases
            # (e.g. "llamacpp:<sha256>") for models already listed by name.
            continue
        seen.add(name)
        details = _field(m, "details")
        families = list(_field(details, "families") or []) if details is not None else []
        try:
            vision = vision_from_show(c.show(name), families)
        except Exception:  # noqa: BLE001
            vision = any(f in _VISION_FAMILIES for f in families)
        out.append({"name": name, "vision": vision})
    return sorted(out, key=lambda x: (not x["vision"], x["name"]))


def list_models_with_vision(*, timeout: float = 1.5) -> list[dict[str, Any]]:
    """Return installed models as ``[{"name", "vision"}]``, vision models first.

    Best-effort: returns [] when Ollama is unreachable.
    """

    return probe_models(timeout=timeout) or []
