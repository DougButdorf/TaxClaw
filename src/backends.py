"""Extraction backends behind one small interface.

Backends (``model_backend`` in config.yaml):

- ``local``              Ollama on this machine (default; nothing leaves the machine)
- ``anthropic``          Anthropic Messages API (``cloud`` is accepted as an alias)
- ``openai_compat``      any OpenAI-compatible Chat Completions endpoint
                         (OpenAI, OpenRouter, Gemini's OpenAI-compatible endpoint, custom)
- ``cloudflare_clairic`` Cloudflare Workers AI ``@cf/cloudflare/clairic`` typed extraction

Every backend implements ``ensure_ready()`` (fail fast, presence-only key
checks) and ``chat_json()`` (image + prompt -> parsed JSON). Backends that can
do typed per-field extraction (Clairic) also implement ``extract_structured()``,
which returns per-field confidences.

API keys are read from environment variables at call time and are never
logged, stored or included in error messages.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from .ai import parse_json_text, privacy_error
from .config import Config, normalize_backend

HTTP_TIMEOUT = httpx.Timeout(180.0, connect=15.0)


@dataclass
class ExtractionResult:
    """Extraction output plus optional per-field confidence (Clairic)."""

    data: Any
    # field path (or path prefix) -> confidence in [0, 1]
    field_confidence: dict[str, float] = field(default_factory=dict)
    # field paths whose confidence / null-probability calls for human review
    review_fields: list[str] = field(default_factory=list)
    method: str = "llm"


def _b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(image_bytes) >= 12 and image_bytes[0:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _short_http_error(resp: httpx.Response) -> str:
    """Provider error text without echoing request headers (keys are only ever in headers)."""

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return f"HTTP {resp.status_code}: {resp.text[:300]}"
    msg: Any = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code")
        elif isinstance(err, str):
            msg = err
        if msg is None and isinstance(data.get("errors"), list) and data["errors"]:
            first = data["errors"][0]
            msg = first.get("message") if isinstance(first, dict) else first
        if msg is None:
            msg = data.get("message")
    return f"HTTP {resp.status_code}: {str(msg if msg is not None else data)[:300]}"


class Backend:
    name = "base"
    is_cloud = True

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def ensure_ready(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _require_privacy_ack(self) -> None:
        # Defense in depth: every cloud backend refuses to run until the user has
        # acknowledged the privacy warning, even when called directly (not via src.ai).
        if self.is_cloud and not self.cfg.privacy_acknowledged:
            raise RuntimeError(privacy_error(self.cfg))

    def chat_json(self, *, prompt: str, image_bytes: bytes, schema: dict[str, Any] | None = None) -> Any:
        raise NotImplementedError  # pragma: no cover

    def supports_structured(self, doc_type: str) -> bool:
        return False

    def extract_structured(self, *, doc_type: str, pages: list[tuple[bytes, str]]) -> ExtractionResult:
        raise NotImplementedError  # pragma: no cover

    def classify_image(self, image_bytes: bytes) -> dict[str, Any] | None:
        """Optional backend-native classification; None = use the prompt path."""

        return None


# ---------------------------------------------------------------------------
# local (Ollama)
# ---------------------------------------------------------------------------


class LocalBackend(Backend):
    name = "local"
    is_cloud = False

    def ensure_ready(self) -> None:
        from .ollama_local import ensure_vision_model

        ensure_vision_model(self.cfg.local_model)

    def _chat(self, *, prompt: str, b64: str, fmt: dict[str, Any] | str) -> str:
        from .ollama_local import client as ollama_client

        resp = ollama_client().chat(
            model=self.cfg.local_model,
            messages=[{"role": "user", "content": prompt, "images": [b64]}],
            options={"temperature": 0},
            format=fmt,
        )
        return resp["message"]["content"]

    def chat_json(self, *, prompt: str, image_bytes: bytes, schema: dict[str, Any] | None = None) -> Any:
        import ollama

        from .ollama_local import LocalModelError, ensure_vision_model, is_connection_error, unreachable_message

        # Ollama multimodal: model must support images (checked up front, cached).
        ensure_vision_model(self.cfg.local_model)
        b64 = _b64(image_bytes)
        try:
            try:
                text = self._chat(prompt=prompt, b64=b64, fmt=schema or "json")
            except ollama.ResponseError as e:
                if not schema or getattr(e, "status_code", None) == 404:
                    raise
                # Older Ollama builds may reject JSON-schema formats; fall back to plain JSON mode.
                text = self._chat(prompt=prompt, b64=b64, fmt="json")
        except LocalModelError:
            raise
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise LocalModelError(unreachable_message()) from None
            raise
        return parse_json_text(text)


# ---------------------------------------------------------------------------
# anthropic
# ---------------------------------------------------------------------------


class AnthropicBackend(Backend):
    name = "anthropic"

    def ensure_ready(self) -> None:
        self._require_privacy_ack()
        if not self.cfg.cloud_api_key:
            raise RuntimeError("Anthropic backend selected but no key found: set the ANTHROPIC_API_KEY environment variable")
        if not self.cfg.cloud_model:
            raise RuntimeError("Anthropic backend selected but cloud_model is empty (e.g. claude-haiku-5-5)")

    def chat_json(self, *, prompt: str, image_bytes: bytes, schema: dict[str, Any] | None = None) -> Any:
        from anthropic import Anthropic

        self.ensure_ready()
        client = Anthropic(api_key=self.cfg.cloud_api_key)
        msg = client.messages.create(
            model=self.cfg.cloud_model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": image_mime(image_bytes), "data": _b64(image_bytes)},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text = "".join([c.text for c in msg.content if getattr(c, "type", None) == "text"])
        return parse_json_text(text)


# ---------------------------------------------------------------------------
# openai_compat (OpenAI, OpenRouter, Gemini OpenAI-compatible endpoint, custom)
# ---------------------------------------------------------------------------


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


class OpenAICompatBackend(Backend):
    name = "openai_compat"

    def __init__(self, cfg: Config, *, transport: httpx.BaseTransport | None = None):
        super().__init__(cfg)
        self._transport = transport

    @property
    def base_url(self) -> str:
        return self.cfg.openai_compat_resolved_base_url()

    def ensure_ready(self) -> None:
        self._require_privacy_ack()
        envs = self.cfg.openai_compat_key_envs()
        if not self.base_url:
            raise RuntimeError("openai_compat backend needs openai_compat_base_url (or a provider preset: openai, openrouter, gemini)")
        if not self.cfg.openai_compat_model:
            raise RuntimeError("openai_compat backend needs openai_compat_model (run `taxclaw models` to list vision models)")
        if not envs:
            raise RuntimeError("openai_compat backend needs openai_compat_api_key_env (the NAME of the env var holding the key)")
        if not self.cfg.openai_compat_api_key():
            raise RuntimeError(f"openai_compat backend: none of these environment variables is set: {', '.join(envs)}")

    def _headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.cfg.openai_compat_api_key()}", "Content-Type": "application/json"}
        if "openrouter.ai" in self.base_url:
            h["X-Title"] = "TaxClaw"
            h["HTTP-Referer"] = "https://github.com/DougButdorf/TaxClaw"
        return h

    @staticmethod
    def response_formats(schema: dict[str, Any] | None) -> list[dict[str, Any] | None]:
        """Structured-output ladder: json_schema -> json_object -> plain (parsed tolerantly)."""

        ladder: list[dict[str, Any] | None] = []
        if schema:
            ladder.append(
                {"type": "json_schema", "json_schema": {"name": "taxclaw_extraction", "schema": schema, "strict": False}}
            )
        ladder.append({"type": "json_object"})
        ladder.append(None)
        return ladder

    def chat_json(self, *, prompt: str, image_bytes: bytes, schema: dict[str, Any] | None = None) -> Any:
        self.ensure_ready()
        data_url = f"data:{image_mime(image_bytes)};base64,{_b64(image_bytes)}"
        base_body: dict[str, Any] = {
            "model": self.cfg.openai_compat_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0,
        }
        url = f"{self.base_url}/chat/completions"
        last_err = "no attempt made"
        with httpx.Client(timeout=HTTP_TIMEOUT, transport=self._transport) as client:
            for rf in self.response_formats(schema):
                body = dict(base_body)
                if rf is not None:
                    body["response_format"] = rf
                resp = client.post(url, headers=self._headers(), json=body)
                if resp.status_code in (400, 422) and "temperature" in resp.text.lower():
                    # Some reasoning models only accept the default temperature.
                    body.pop("temperature", None)
                    resp = client.post(url, headers=self._headers(), json=body)
                if resp.status_code in (400, 404, 422) and rf is not None:
                    last_err = _short_http_error(resp)
                    continue  # provider/model rejects this response_format; step down the ladder
                if resp.status_code >= 400:
                    raise RuntimeError(f"openai_compat request failed: {_short_http_error(resp)}")
                payload = resp.json()
                try:
                    content = payload["choices"][0]["message"].get("content")
                except (KeyError, IndexError, TypeError):
                    raise RuntimeError(f"openai_compat: unexpected response shape (keys: {list(payload)[:5]})") from None
                return parse_json_text(_message_text(content))
        raise RuntimeError(f"openai_compat request failed: {last_err}")


# ---------------------------------------------------------------------------
# cloudflare_clairic
# ---------------------------------------------------------------------------


class ClairicBackend(Backend):
    """Cloudflare Workers AI Clairic: typed fields with per-field confidence.

    Free-form prompts (generic/1040 extraction, 1099-DA transaction tables)
    go to ``clairic_fallback_backend`` (``local`` by default), because Clairic
    is a typed-field model, not a chat model.
    """

    name = "cloudflare_clairic"
    MODEL = "@cf/cloudflare/clairic"

    def __init__(self, cfg: Config, *, transport: httpx.BaseTransport | None = None):
        super().__init__(cfg)
        self._transport = transport

    def ensure_ready(self) -> None:
        self._require_privacy_ack()
        missing = []
        if not self.cfg.cloudflare_resolved_account_id():
            missing.append("CLOUDFLARE_ACCOUNT_ID (env) or cloudflare_account_id (config)")
        if not self.cfg.cloudflare_api_token():
            missing.append(f"{self.cfg.cloudflare_api_token_env or 'CLOUDFLARE_API_TOKEN'} (env)")
        if missing:
            raise RuntimeError("cloudflare_clairic backend is missing: " + "; ".join(missing) + ". See `taxclaw models` tier 3 for setup.")

    @property
    def url(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self.cfg.cloudflare_resolved_account_id()}/ai/run/{self.MODEL}"

    def fallback(self) -> Backend:
        fb = normalize_backend(self.cfg.clairic_fallback_backend)
        if fb == self.name:
            fb = "local"
        return get_backend(self.cfg, override=fb)

    def run(self, body: dict[str, Any]) -> dict[str, Any]:
        self.ensure_ready()
        headers = {"Authorization": f"Bearer {self.cfg.cloudflare_api_token()}", "Content-Type": "application/json"}
        with httpx.Client(timeout=HTTP_TIMEOUT, transport=self._transport) as client:
            resp = client.post(self.url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"Clairic request failed: {_short_http_error(resp)}")
        payload = resp.json()
        # Workers AI REST wraps model output as {"result": {...}, "success": true, ...};
        # the Workers binding returns the bare object. Accept both.
        if isinstance(payload, dict) and "answers" not in payload and isinstance(payload.get("result"), dict):
            if payload.get("success") is False:
                raise RuntimeError(f"Clairic request failed: {payload.get('errors')}")
            payload = payload["result"]
        if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
            raise RuntimeError("Clairic response had no 'answers' object")
        return payload

    # prompt path -> fallback backend
    def chat_json(self, *, prompt: str, image_bytes: bytes, schema: dict[str, Any] | None = None) -> Any:
        fb = self.fallback()
        try:
            fb.ensure_ready()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"This step needs a free-form model, which Clairic is not; the fallback backend "
                f"'{fb.name}' (clairic_fallback_backend) is not ready: {e}"
            ) from None
        return fb.chat_json(prompt=prompt, image_bytes=image_bytes, schema=schema)

    def supports_structured(self, doc_type: str) -> bool:
        from .clairic import supports_doc_type

        return supports_doc_type(doc_type)

    def extract_structured(self, *, doc_type: str, pages: list[tuple[bytes, str]]) -> ExtractionResult:
        from .clairic import extract_with_clairic

        return extract_with_clairic(
            doc_type=doc_type,
            pages=pages,
            run=self.run,
            threshold=float(self.cfg.review_confidence_threshold),
        )

    def classify_image(self, image_bytes: bytes) -> dict[str, Any] | None:
        from .clairic import classify_with_clairic

        return classify_with_clairic(image_bytes=image_bytes, run=self.run)


_BACKENDS: dict[str, type[Backend]] = {
    "local": LocalBackend,
    "anthropic": AnthropicBackend,
    "openai_compat": OpenAICompatBackend,
    "cloudflare_clairic": ClairicBackend,
}


def get_backend(cfg: Config, *, override: str | None = None) -> Backend:
    name = normalize_backend(override or cfg.model_backend)
    return _BACKENDS[name](cfg)
