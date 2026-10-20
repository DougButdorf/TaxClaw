from __future__ import annotations

import os
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PRIVACY_WARNING = """> ⚠️ PRIVACY WARNING: You have configured TaxClaw to use a cloud-hosted AI model. Tax documents contain sensitive personal and financial information including Social Security Numbers, income, and asset holdings. When using cloud models, document content is transmitted to a third-party AI provider outside your local control. This provider may log requests for safety monitoring. For maximum privacy, use local models (the default). Only continue if you understand and accept this. Set `privacy_acknowledged: true` in config.yaml to confirm.
"""

# Extraction backends. "cloud" is the pre-1.0 name for the Anthropic backend and
# is still accepted in config files.
LOCAL_BACKEND = "local"
BACKENDS: tuple[str, ...] = ("local", "anthropic", "openai_compat", "cloudflare_clairic")
BACKEND_ALIASES: dict[str, str] = {"cloud": "anthropic"}

# Presets for the OpenAI-compatible backend. Only env var NAMES live here;
# TaxClaw never stores key values in config.yaml.
OPENAI_COMPAT_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "key_envs": ["OPENAI_API_KEY"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key_envs": ["OPENROUTER_API_KEY"],
    },
    "gemini": {
        "label": "Google Gemini (OpenAI-compatible endpoint)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_envs": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    },
    "custom": {
        "label": "Custom OpenAI-compatible endpoint",
        "base_url": "",
        "key_envs": [],
    },
}


def normalize_backend(name: str | None) -> str:
    """Map config values (including the legacy ``cloud``) to a backend id."""

    n = (name or LOCAL_BACKEND).strip().lower()
    n = BACKEND_ALIASES.get(n, n)
    return n if n in BACKENDS else LOCAL_BACKEND


def is_cloud_backend(name: str | None) -> bool:
    """Every backend except ``local`` sends document content off this machine."""

    return normalize_backend(name) != LOCAL_BACKEND


def _expand_path(p: str) -> str:
    return str(Path(os.path.expanduser(p)).expanduser())


@dataclass
class Config:
    model_backend: str = "local"  # local|anthropic|openai_compat|cloudflare_clairic ("cloud" = anthropic)
    local_model: str = "gemma3:4b"  # must be a vision-capable Ollama model
    cloud_model: str = "claude-haiku-5-5"  # Anthropic model id
    cloud_api_key: str = ""  # Anthropic key; prefer the ANTHROPIC_API_KEY env var
    privacy_acknowledged: bool = False
    # Consent record, written together with privacy_acknowledged by `taxclaw use-cloud`
    # and the Settings page: when (UTC, ISO 8601) and for which provider the user agreed
    # to send documents off this machine. Both are empty while the backend is local.
    privacy_acknowledged_at: str = ""
    cloud_provider: str = ""
    port: int = 8421
    data_dir: str = "~/.local/share/taxclaw/"

    # OpenAI-compatible backend (OpenAI, OpenRouter, Gemini, custom).
    openai_compat_provider: str = "openai"  # openai|openrouter|gemini|custom
    openai_compat_model: str = ""
    openai_compat_base_url: str = ""  # empty = provider preset
    openai_compat_api_key_env: str = ""  # env var NAME holding the key; empty = provider preset

    # Cloudflare Workers AI Clairic backend.
    cloudflare_account_id: str = ""  # empty = CLOUDFLARE_ACCOUNT_ID env var
    cloudflare_api_token_env: str = "CLOUDFLARE_API_TOKEN"  # env var NAME holding the token
    clairic_fallback_backend: str = "local"  # used for transaction tables, generic forms, free-form prompts
    review_confidence_threshold: float = 0.8  # per-field confidence below this flags the document for review

    # Security limits
    max_upload_bytes: int = 10 * 1024 * 1024  # 10MB
    storage_cap_bytes: int = 2 * 1024 * 1024 * 1024  # 2GB total stored originals

    @property
    def backend(self) -> str:
        return normalize_backend(self.model_backend)

    @property
    def is_cloud(self) -> bool:
        return is_cloud_backend(self.model_backend)

    @property
    def data_path(self) -> Path:
        return Path(_expand_path(self.data_dir))

    @property
    def db_path(self) -> Path:
        return self.data_path / "tax.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_path / "uploads"

    # -- OpenAI-compatible helpers ------------------------------------------

    @property
    def openai_compat_preset(self) -> dict[str, Any]:
        return OPENAI_COMPAT_PRESETS.get(self.openai_compat_provider, OPENAI_COMPAT_PRESETS["custom"])

    def openai_compat_resolved_base_url(self) -> str:
        return (self.openai_compat_base_url or self.openai_compat_preset.get("base_url") or "").rstrip("/")

    def openai_compat_key_envs(self) -> list[str]:
        if self.openai_compat_api_key_env:
            return [self.openai_compat_api_key_env]
        return list(self.openai_compat_preset.get("key_envs") or [])

    def openai_compat_api_key(self) -> str:
        for name in self.openai_compat_key_envs():
            val = os.environ.get(name, "")
            if val:
                return val
        return ""

    # -- Cloudflare helpers ---------------------------------------------------

    def cloudflare_resolved_account_id(self) -> str:
        return self.cloudflare_account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

    def cloudflare_api_token(self) -> str:
        return os.environ.get(self.cloudflare_api_token_env or "CLOUDFLARE_API_TOKEN", "")

    def provider_name(self) -> str:
        """Who receives the documents: ``ollama`` (this machine) or the cloud provider's name."""

        b = self.backend
        if b == "local":
            return "ollama"
        if b == "anthropic":
            return "anthropic"
        if b == "openai_compat":
            base = self.openai_compat_base_url.strip()
            if self.openai_compat_provider == "custom" or base:
                from urllib.parse import urlsplit

                host = urlsplit(self.openai_compat_resolved_base_url()).hostname or "unknown-host"
                return f"custom:{host}" if self.openai_compat_provider == "custom" else f"{self.openai_compat_provider} (custom URL {host})"
            return self.openai_compat_provider
        return "cloudflare"

    def model_name(self) -> str:
        """The model id alone (no provider prefix); empty when none is set."""

        b = self.backend
        if b == "local":
            return self.local_model
        if b == "anthropic":
            return self.cloud_model
        if b == "openai_compat":
            return self.openai_compat_model
        return "@cf/cloudflare/clairic"

    def selected_model_label(self) -> str:
        """Human-readable "backend / model" for status lines (never includes secrets)."""

        b = self.backend
        if b == "local":
            return self.local_model
        if b == "anthropic":
            return self.cloud_model
        if b == "openai_compat":
            return f"{self.openai_compat_provider}:{self.openai_compat_model or '(no model set)'}"
        return "@cf/cloudflare/clairic"


CONFIG_PATH = Path(os.path.expanduser("~/.config/taxclaw/config.yaml"))


def load_config(*, create_dirs: bool = True) -> Config:
    """Read config.yaml. ``create_dirs=False`` keeps the call free of side effects (used by ``taxclaw doctor``)."""

    cfg_path = CONFIG_PATH
    if cfg_path.exists():
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text()) or {}
    else:
        raw = {}

    known = {f.name for f in fields(Config)}
    cfg = Config(**{k: v for k, v in raw.items() if k in known})
    cfg.model_backend = normalize_backend(cfg.model_backend)
    cfg.privacy_acknowledged_at = str(cfg.privacy_acknowledged_at or "")
    cfg.cloud_provider = str(cfg.cloud_provider or "")

    # allow env var override
    if not cfg.cloud_api_key:
        cfg.cloud_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # NOTE: Do not hard-exit here; the web UI needs to load even if the user
    # hasn't acknowledged cloud privacy yet. Enforce acknowledgement at call sites.

    if create_dirs:
        cfg.data_path.mkdir(parents=True, exist_ok=True)
        cfg.uploads_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def cloud_api_key_in_config_file() -> bool:
    """Presence check only: is a non-empty ``cloud_api_key`` written in config.yaml?"""

    if not CONFIG_PATH.exists():
        return False
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except Exception:  # noqa: BLE001
        return False
    return bool(isinstance(raw, dict) and raw.get("cloud_api_key"))


def save_config(*, cfg: Config) -> None:
    """Persist user-editable config fields to ~/.config/taxclaw/config.yaml.

    Intentionally does not write cloud_api_key (prefer env var), and will preserve
    unknown keys already present in the file.
    """

    cfg_path = CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if cfg_path.exists():
        existing = yaml.safe_load(cfg_path.read_text()) or {}

    existing.update(
        {
            "model_backend": normalize_backend(cfg.model_backend),
            "local_model": cfg.local_model,
            "cloud_model": cfg.cloud_model,
            "openai_compat_provider": cfg.openai_compat_provider,
            "openai_compat_model": cfg.openai_compat_model,
            "openai_compat_base_url": cfg.openai_compat_base_url,
            "openai_compat_api_key_env": cfg.openai_compat_api_key_env,
            "cloudflare_account_id": cfg.cloudflare_account_id,
            "cloudflare_api_token_env": cfg.cloudflare_api_token_env,
            "clairic_fallback_backend": cfg.clairic_fallback_backend,
            "review_confidence_threshold": float(cfg.review_confidence_threshold),
            "privacy_acknowledged": bool(cfg.privacy_acknowledged),
            "privacy_acknowledged_at": cfg.privacy_acknowledged_at or "",
            "cloud_provider": cfg.cloud_provider or "",
            "port": int(cfg.port),
            "data_dir": cfg.data_dir,
            "max_upload_bytes": int(cfg.max_upload_bytes),
            "storage_cap_bytes": int(cfg.storage_cap_bytes),
        }
    )

    cfg_path.write_text(yaml.safe_dump(existing, sort_keys=False))


# ---------------------------------------------------------------------------
# Consent record (the only place cloud consent is written)
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record_cloud_consent(cfg: Config, *, keep_existing: bool = False) -> None:
    """Stamp consent on ``cfg`` for its current (cloud) backend: flag, UTC time, provider name.

    ``keep_existing`` leaves the original timestamp alone when the user already consented to
    this same provider (used when Settings is saved again without changing the cloud choice).
    """

    provider = cfg.provider_name()
    if not (keep_existing and cfg.privacy_acknowledged and cfg.privacy_acknowledged_at and cfg.cloud_provider == provider):
        cfg.privacy_acknowledged_at = utc_now_iso()
    cfg.privacy_acknowledged = True
    cfg.cloud_provider = provider


def clear_cloud_consent(cfg: Config) -> None:
    """Withdraw consent: any switch back to local clears the flag, timestamp and provider."""

    cfg.privacy_acknowledged = False
    cfg.privacy_acknowledged_at = ""
    cfg.cloud_provider = ""
