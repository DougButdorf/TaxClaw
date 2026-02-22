from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PRIVACY_WARNING = """> ⚠️ PRIVACY WARNING: You have configured TaxClaw to use a cloud-hosted AI model. Tax documents contain sensitive personal and financial information including Social Security Numbers, income, and asset holdings. When using cloud models, document content is transmitted to a third-party AI provider outside your local control. This provider may log requests for safety monitoring. For maximum privacy, use local models (the default). Only continue if you understand and accept this. Set `privacy_acknowledged: true` in config.yaml to confirm.
"""


def _expand_path(p: str) -> str:
    return str(Path(os.path.expanduser(p)).expanduser())


@dataclass
class Config:
    model_backend: str = "local"  # local|cloud
    local_model: str = "llama3.2"
    cloud_model: str = "claude-haiku-4-5"
    cloud_api_key: str = ""
    privacy_acknowledged: bool = False
    port: int = 8421
    data_dir: str = "~/.local/share/taxclaw/"

    @property
    def data_path(self) -> Path:
        return Path(_expand_path(self.data_dir))

    @property
    def db_path(self) -> Path:
        return self.data_path / "tax.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_path / "uploads"


def load_config() -> Config:
    cfg_path = Path(os.path.expanduser("~/.config/taxclaw/config.yaml"))
    if cfg_path.exists():
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text()) or {}
    else:
        raw = {}

    cfg = Config(**{k: v for k, v in raw.items() if hasattr(Config, k)})

    # allow env var override
    if not cfg.cloud_api_key:
        cfg.cloud_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if cfg.model_backend == "cloud" and not cfg.privacy_acknowledged:
        # Print and exit early to force explicit opt-in.
        print(PRIVACY_WARNING)
        raise SystemExit(2)

    cfg.data_path.mkdir(parents=True, exist_ok=True)
    cfg.uploads_dir.mkdir(parents=True, exist_ok=True)
    return cfg
