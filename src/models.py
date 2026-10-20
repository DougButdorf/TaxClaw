"""Three-tier model selection: local-first, cloud already configured, strongest with setup.

Data (recommendations, heuristics, setup text) lives in ``model_catalog.yaml``;
this module does the live detection:

- Tier 1: installed Ollama models that can read images, machine RAM, and the
  catalog's RAM-bucket recommendation (+ ``ollama pull`` for missing ones).
- Tier 2: cloud credentials by PRESENCE ONLY (env vars and ``cloud_api_key`` in
  config.yaml); provider NAMES from OpenClaw config files; live model lists
  (vision-capable) for providers whose key is present.
- Tier 3: Cloudflare Clairic setup and status.

Key values are only ever placed in HTTP request headers to the provider's own
API. They are never printed, logged, returned or stored.
"""

from __future__ import annotations

import glob
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml

from .config import OPENAI_COMPAT_PRESETS, Config, cloud_api_key_in_config_file

CATALOG_PATH = Path(__file__).with_name("model_catalog.yaml")
LIST_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
LIST_CACHE_SECONDS = 600
# provider id -> (monotonic time, listing). Model lists only; never keys.
_LIST_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return yaml.safe_load(CATALOG_PATH.read_text()) or {}


# ---------------------------------------------------------------------------
# Tier 1: local
# ---------------------------------------------------------------------------


def machine_ram_gb() -> float | None:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 1)
    except (AttributeError, ValueError, OSError):
        return None


def _bucket_for(ram_gb: float | None, buckets: list[dict[str, Any]]) -> dict[str, Any]:
    if ram_gb is None:
        # Unknown RAM: use the reference-machine bucket.
        return next((b for b in buckets if b.get("max_ram_gb") and b["max_ram_gb"] > 8), buckets[0])
    for b in buckets:
        mx = b.get("max_ram_gb")
        if mx is None or ram_gb <= mx:
            return b
    return buckets[-1]


def _with_tag(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def tier1_local(cfg: Config, *, ollama_models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from .ollama_local import list_models_with_vision, ollama_host

    cat = load_catalog().get("tier1_local") or {}
    ram = machine_ram_gb()
    bucket = _bucket_for(ram, cat.get("ram_buckets") or [])
    models = ollama_models if ollama_models is not None else list_models_with_vision(timeout=2.0)
    installed = {_with_tag(m["name"]) for m in models}
    vision = [m["name"] for m in models if m.get("vision")]
    text_only = [m["name"] for m in models if not m.get("vision")]

    recs = []
    for role in ("default", "accuracy"):
        name = bucket.get(role)
        if not name or any(r["model"] == name for r in recs):
            continue
        is_installed = _with_tag(name) in installed
        recs.append(
            {
                "role": role,
                "model": name,
                "installed": is_installed,
                "pull_command": None if is_installed else f"ollama pull {name}",
            }
        )

    return {
        "tier": 1,
        "title": cat.get("title"),
        "status": cat.get("status"),
        "reference_machine": cat.get("reference_machine"),
        "machine_ram_gb": ram,
        "ram_bucket": bucket.get("label"),
        "bucket_note": bucket.get("note"),
        "ollama_host": ollama_host(),
        "ollama_reachable": bool(models),
        "vision_models_installed": vision,
        "text_only_models_installed": text_only,
        "recommended": recs,
        "known_weak": cat.get("known_weak") or [],
        "current_local_model": cfg.local_model,
        "current_local_model_is_vision": _with_tag(cfg.local_model) in {_with_tag(v) for v in vision},
    }


# ---------------------------------------------------------------------------
# Tier 2: cloud already configured
# ---------------------------------------------------------------------------


def _present(name: str) -> bool:
    return bool(os.environ.get(name))


def openclaw_config_paths() -> list[Path]:
    """OpenClaw config files to read provider NAMES from (never values)."""

    paths: list[Path] = []
    explicit = os.environ.get("OPENCLAW_CONFIG_PATH")
    if explicit:
        paths.append(Path(explicit).expanduser())
    state = os.environ.get("OPENCLAW_STATE_DIR")
    if state:
        paths.append(Path(state).expanduser() / "openclaw.json")
    home = Path.home()
    paths.append(home / ".openclaw" / "openclaw.json")
    paths.extend(Path(p) for p in sorted(glob.glob(str(home / ".openclaw-*" / "openclaw.json"))))
    seen: set[str] = set()
    out = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen or not p.is_file():
            continue
        seen.add(key)
        out.append(p)
    return out


def openclaw_provider_names() -> list[dict[str, Any]]:
    """Provider names configured in OpenClaw (``models.providers`` keys). Names only."""

    found: set[str] = set()
    for p in openclaw_config_paths():
        try:
            data = json.loads(p.read_text())
        except Exception:  # noqa: BLE001 - JSON5 or unreadable: skip silently
            continue
        providers = ((data.get("models") or {}).get("providers") or {}) if isinstance(data, dict) else {}
        if isinstance(providers, dict):
            found.update(str(name) for name in providers)
    return [{"provider": n} for n in sorted(found)]


_DATE_SUFFIX = re.compile(r"(-\d{4}-\d{2}-\d{2}|-\d{8}|-\d{4})$")


def _version_key(model_id: str) -> tuple:
    base = model_id.split("/")[-1]
    dated = bool(_DATE_SUFFIX.search(base))
    base = _DATE_SUFFIX.sub("", base)
    preview = any(t in base for t in ("preview", "exp", "experimental"))
    nums = tuple(int(n) for n in re.findall(r"\d+", base)[:4])
    # higher version first, then undated alias, then non-preview
    return (nums, not dated, not preview)


def pick_by_patterns(ids: list[str], patterns: list[str]) -> str | None:
    for pat in patterns or []:
        rx = re.compile(pat)
        matches = [i for i in ids if rx.search(i)]
        if matches:
            return max(matches, key=_version_key)
    return None


def _filter_vision(ids: list[str], include: list[str] | None, exclude: list[str] | None) -> list[str]:
    out = []
    for i in ids:
        if include and not any(re.search(p, i) for p in include):
            continue
        if exclude and any(x in i for x in exclude):
            continue
        out.append(i)
    return out


def _get_json(client: httpx.Client, url: str, headers: dict[str, str]) -> Any:
    resp = client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.json()


def list_provider_models(
    provider: str,
    spec: dict[str, Any],
    *,
    cfg: Config | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Live vision-model list for one provider whose key is present."""

    with httpx.Client(timeout=LIST_TIMEOUT, transport=transport) as client:
        if provider == "anthropic":
            key = (cfg.cloud_api_key if cfg else "") or os.environ.get("ANTHROPIC_API_KEY", "")
            url = spec["models_api"] + "?limit=1000"
            data = _get_json(client, url, {"x-api-key": key, "anthropic-version": "2023-06-01"})
            ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
            return {"models": sorted(ids), "vision_basis": "all current Claude models accept images"}
        if provider == "openai":
            key = os.environ.get("OPENAI_API_KEY", "")
            data = _get_json(client, spec["models_api"], {"Authorization": f"Bearer {key}"})
            ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
            return {"models": sorted(_filter_vision(ids, spec.get("vision_include"), spec.get("vision_exclude"))), "vision_basis": spec.get("vision_note")}
        if provider == "gemini":
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
            ids = []
            page_token = None
            for _ in range(10):
                url = spec["models_api"] + "?pageSize=1000" + (f"&pageToken={page_token}" if page_token else "")
                data = _get_json(client, url, {"x-goog-api-key": key})
                for m in data.get("models", []):
                    if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                        continue
                    ids.append(str(m.get("name", "")).removeprefix("models/"))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            return {"models": sorted(_filter_vision(ids, spec.get("vision_include"), spec.get("vision_exclude"))), "vision_basis": spec.get("vision_note")}
        if provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "")
            data = _get_json(client, spec["models_api"], {"Authorization": f"Bearer {key}"})
            ids = []
            for m in data.get("data", []):
                mods = ((m.get("architecture") or {}).get("input_modalities")) or []
                if "image" in mods and m.get("id"):
                    ids.append(m["id"])
            return {"models": sorted(ids), "vision_basis": spec.get("vision_note")}
    raise RuntimeError(f"no model-list API for {provider}")


def tier2_cloud(cfg: Config, *, live: bool = True, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    cat = load_catalog().get("tier2_cloud") or {}
    providers_out = []
    for pid, spec in (cat.get("providers") or {}).items():
        envs = spec.get("env") or []
        env_presence = {e: _present(e) for e in envs}
        if spec.get("env_all_required"):
            configured = all(env_presence.values())
        else:
            configured = any(env_presence.values())
        entry: dict[str, Any] = {
            "provider": pid,
            "label": spec.get("label"),
            "env_presence": env_presence,
            "configured": configured,
            "backend": spec.get("backend"),
        }
        if pid == "anthropic":
            in_cfg = cloud_api_key_in_config_file()
            entry["config_cloud_api_key_present"] = in_cfg
            entry["configured"] = configured or in_cfg
        if spec.get("provider_preset"):
            preset = spec["provider_preset"]
            entry["openai_compat_provider"] = preset
            entry["base_url"] = OPENAI_COMPAT_PRESETS.get(preset, {}).get("base_url")
        if spec.get("note"):
            entry["note"] = spec["note"]

        confirmed = spec.get("confirmed") or {}
        if confirmed:
            entry["recommended"] = {
                "balance": confirmed.get("balance"),
                "strongest": confirmed.get("strongest"),
                "basis": spec.get("confirmed_note") or "confirmed model IDs",
            }

        if live and configured and spec.get("models_api"):
            try:
                cached = _LIST_CACHE.get(pid) if transport is None else None
                if cached and time.monotonic() - cached[0] < LIST_CACHE_SECONDS:
                    listed = cached[1]
                else:
                    listed = list_provider_models(pid, spec, cfg=cfg, transport=transport)
                    if transport is None:
                        _LIST_CACHE[pid] = (time.monotonic(), listed)
                entry["vision_models"] = listed["models"]
                entry["vision_basis"] = listed.get("vision_basis")
                if not confirmed:
                    entry["recommended"] = {
                        "balance": pick_by_patterns(listed["models"], spec.get("balance_patterns") or []),
                        "strongest": pick_by_patterns(listed["models"], spec.get("strongest_patterns") or []),
                        "basis": cat.get("heuristic_label"),
                    }
                else:
                    entry["recommended"]["in_live_list"] = {
                        role: (mid in listed["models"]) for role, mid in confirmed.items() if mid
                    }
            except Exception as e:  # noqa: BLE001
                entry["list_error"] = str(e)[:200]
        elif configured and spec.get("models_api") and not live:
            entry["vision_models"] = None
            entry["list_skipped"] = "offline mode"
        providers_out.append(entry)

    return {
        "tier": 2,
        "title": cat.get("title"),
        "presence_only": True,
        "providers": providers_out,
        "openclaw_providers": [
            dict(p, note="configured in OpenClaw; export the key to TaxClaw's environment to use it")
            for p in openclaw_provider_names()
        ],
        "privacy": "Cloud backends send document content off this machine and require privacy_acknowledged: true.",
    }


# ---------------------------------------------------------------------------
# Tier 3: strongest with setup
# ---------------------------------------------------------------------------


def tier3_setup(cfg: Config) -> dict[str, Any]:
    cat = load_catalog().get("tier3_setup") or {}
    opts = []
    for o in cat.get("options") or []:
        entry = dict(o)
        if o.get("id") == "cloudflare_clairic":
            entry["env_presence"] = {
                "CLOUDFLARE_ACCOUNT_ID": _present("CLOUDFLARE_ACCOUNT_ID") or bool(cfg.cloudflare_account_id),
                cfg.cloudflare_api_token_env or "CLOUDFLARE_API_TOKEN": _present(cfg.cloudflare_api_token_env or "CLOUDFLARE_API_TOKEN"),
            }
            entry["configured"] = all(entry["env_presence"].values())
        opts.append(entry)
    return {"tier": 3, "title": cat.get("title"), "options": opts}


def build_report(cfg: Config, *, live: bool = True, ollama_models: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cat = load_catalog()
    return {
        "catalog": {"source": cat.get("source"), "as_of": cat.get("as_of"), "path": "src/model_catalog.yaml"},
        "current": {
            "model_backend": cfg.backend,
            "model": cfg.selected_model_label(),
            "privacy_acknowledged": bool(cfg.privacy_acknowledged),
            "is_cloud": cfg.is_cloud,
        },
        "tiers": [
            tier1_local(cfg, ollama_models=ollama_models),
            tier2_cloud(cfg, live=live),
            tier3_setup(cfg),
        ],
    }


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


def _yn(v: bool) -> str:
    return "yes" if v else "no"


def format_report(report: dict[str, Any], *, short: bool = False) -> str:
    t1, t2, t3 = report["tiers"]
    cur = report["current"]
    lines = [f"Current backend: {cur['model_backend']} ({cur['model']})"]
    lines.append("")
    lines.append(f"Tier 1 - {t1['title']} [{t1['status']}]")
    ram = f"{t1['machine_ram_gb']} GB" if t1["machine_ram_gb"] else "unknown RAM"
    lines.append(f"  This machine: {ram} -> {t1['ram_bucket']}")
    if not t1["ollama_reachable"]:
        lines.append(f"  Ollama: not reachable at {t1['ollama_host']} (start it with `ollama serve` or the Ollama app)")
    else:
        lines.append(f"  Vision models installed: {', '.join(t1['vision_models_installed']) or 'none'}")
    for r in t1["recommended"]:
        state = "installed" if r["installed"] else f"not installed -> {r['pull_command']}"
        lines.append(f"  Recommended ({r['role']}): {r['model']} ({state})")
    if t1.get("bucket_note") and not short:
        lines.append(f"  Note: {t1['bucket_note']}")

    lines.append("")
    lines.append(f"Tier 2 - {t2['title']} (key presence only; values never shown)")
    for p in t2["providers"]:
        pres = ", ".join(f"{k}={'set' if v else 'unset'}" for k, v in p["env_presence"].items())
        if p.get("config_cloud_api_key_present"):
            pres += ", config cloud_api_key=set"
        lines.append(f"  {p['label']}: {'configured' if p['configured'] else 'not configured'} ({pres})")
        if not p["configured"]:
            continue
        rec = p.get("recommended") or {}
        if rec:
            lines.append(f"    recommended: balance={rec.get('balance')} strongest={rec.get('strongest')} [{rec.get('basis')}]")
        if p.get("list_error"):
            lines.append(f"    live model list failed: {p['list_error']}")
        elif p.get("vision_models") is not None and not short:
            vm = p["vision_models"]
            lines.append(f"    vision models ({len(vm)}): {', '.join(vm[:12])}{' ...' if len(vm) > 12 else ''}")
    for oc in t2["openclaw_providers"]:
        lines.append(f"  OpenClaw provider '{oc['provider']}': {oc['note']}")

    lines.append("")
    lines.append(f"Tier 3 - {t3['title']}")
    for o in t3["options"]:
        lines.append(f"  {o['label']}: {'configured' if o.get('configured') else 'not configured'}; {o.get('pricing')}")
        lines.append(f"    status: {o.get('status')}")
        if not short:
            for i, step in enumerate(o.get("setup") or [], 1):
                lines.append(f"    {i}. {step}")
    lines.append("")
    lines.append(f"Recommendations: {report['catalog']['source']} (as of {report['catalog']['as_of']})")
    return "\n".join(lines) + "\n"
