"""First-run doctor: read-only checks and three explicit paths.

``taxclaw doctor`` (alias ``setup``), the Settings page and the MCP ``setup_status`` tool
all render the report built here.

Product rule: TaxClaw never silently switches from local to cloud. The doctor only
READS: it never installs, pulls a model, writes config or contacts a provider. Switching
to cloud is the separate, explicit ``taxclaw use-cloud <backend> --accept-privacy``
command, which records consent. Nothing in this module (or any MCP tool) sets consent.

Data (install links, approximate model sizes, the cloud ordering, the hosted-offer flag
and its pricing text) lives in ``model_catalog.yaml``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import models as _models
from .config import Config, clear_cloud_consent, load_config, record_cloud_consent
from .ollama_local import ollama_host, probe_models

DOCTOR_VERSION = 1

AGENT_RULES = [
    "Do not run install or pull commands (brew, curl, ollama pull) without the user's OK.",
    "Never choose cloud on the user's behalf: present the three paths and let the user pick.",
    "Only the user switches to cloud, with `taxclaw use-cloud ... --accept-privacy` or the Settings page. No MCP tool does it.",
]

STATE_LABELS = {
    "ollama_missing": "NOT READY - Ollama is not installed",
    "server_unreachable": "NOT READY - Ollama is installed but its server is not reachable",
    "no_vision_model": "NOT READY - Ollama is running but has no model that can read images",
    "model_not_selected": "NOT READY - Ollama has a vision model, but TaxClaw is set to a different one",
    "ready": "READY",
}

# Names `taxclaw use-cloud` accepts -> (config backend, openai_compat preset, catalog provider id).
CLOUD_CHOICES: dict[str, tuple[str, str | None, str]] = {
    "anthropic": ("anthropic", None, "anthropic"),
    "openai": ("openai_compat", "openai", "openai"),
    "gemini": ("openai_compat", "gemini", "gemini"),
    "openrouter": ("openai_compat", "openrouter", "openrouter"),
    "cloudflare_clairic": ("cloudflare_clairic", None, "cloudflare"),
}
CLOUD_CHOICE_ALIASES = {"cloudflare": "cloudflare_clairic", "cloud": "anthropic"}

CLAIRIC_MODEL = "@cf/cloudflare/clairic"


# ---------------------------------------------------------------------------
# Probes (small seams so tests never touch the real machine)
# ---------------------------------------------------------------------------


def find_ollama_binary() -> str | None:
    return shutil.which("ollama")


def probe_ollama() -> list[dict[str, Any]] | None:
    """Installed models, or None when the server is not reachable."""

    return probe_models(timeout=2.0)


def ram_gb() -> float | None:
    return _models.machine_ram_gb()


def free_disk_gb() -> float | None:
    raw = (os.environ.get("OLLAMA_MODELS") or "").strip()
    path = Path(raw).expanduser() if raw else Path.home() / ".ollama"
    while not path.exists() and path != path.parent:
        path = path.parent
    try:
        return round(shutil.disk_usage(path).free / (1024**3), 1)
    except OSError:
        return None


def _is_loopback(host_url: str) -> bool:
    host = (urlsplit(host_url).hostname or "").lower()
    return host in ("localhost", "::1", "0.0.0.0") or host.startswith("127.")


def _tag(name: str) -> str:
    return _models._with_tag(name)


# ---------------------------------------------------------------------------
# Path 1: local
# ---------------------------------------------------------------------------


def _requirements(model: str) -> dict[str, Any]:
    reqs = ((_models.load_catalog().get("doctor") or {}).get("model_requirements")) or {}
    return reqs.get(model) or {}


def _fmt_gb(v: float) -> str:
    return f"{v:g}"


def _warnings(model: str, *, installed: bool, ram: float | None, free: float | None) -> list[str]:
    """RAM / disk warnings for ``model`` (only meaningful when Ollama runs on this machine)."""

    cat = _models.load_catalog().get("doctor") or {}
    req = _requirements(model)
    out: list[str] = []
    min_ram = req.get("min_ram_gb")
    if ram is not None and min_ram and ram < min_ram:
        out.append(
            f"This machine has {_fmt_gb(ram)} GB of RAM; {model} needs about {_fmt_gb(min_ram)} GB (approx.). "
            "Expect slow or failed runs. The cloud path with your own keys (path 2) may suit this machine better, "
            "but only you can choose it."
        )
    size = req.get("approx_download_gb")
    headroom = float(cat.get("disk_headroom_gb") or 0)
    if not installed and free is not None and size and free < size + headroom:
        out.append(
            f"Only {_fmt_gb(free)} GB of disk is free; {model} is an approx. {_fmt_gb(size)} GB download and "
            f"needs about {_fmt_gb(headroom)} GB of headroom on top. Free up space before pulling it."
        )
    return out


def _suggest_installed(vision: list[str], bucket: dict[str, Any], known_weak: list[str]) -> str:
    tags = {_tag(v): v for v in vision}
    for role in ("default", "accuracy"):
        name = bucket.get(role)
        if name and _tag(name) in tags:
            return tags[_tag(name)]
    weak = {_tag(w) for w in known_weak}
    for v in vision:
        if _tag(v) not in weak and v.split(":")[0] not in weak:
            return v
    return vision[0]


def local_status(cfg: Config) -> dict[str, Any]:
    cat = _models.load_catalog()
    t1 = cat.get("tier1_local") or {}
    dcat = cat.get("doctor") or {}
    install = dcat.get("install") or {}
    host = ollama_host()
    loopback = _is_loopback(host)
    ram = ram_gb()
    free = free_disk_gb() if loopback else None
    bucket = _models._bucket_for(ram, t1.get("ram_buckets") or [])
    rec_name = bucket.get("default") or cfg.local_model
    binary = find_ollama_binary()
    probed = probe_ollama()
    known_weak = [w.get("model", "") for w in (t1.get("known_weak") or [])]

    vision = [m["name"] for m in (probed or []) if m.get("vision")]
    text_only = [m["name"] for m in (probed or []) if not m.get("vision")]
    rec_installed = _tag(rec_name) in {_tag(v) for v in vision}
    size = _requirements(rec_name).get("approx_download_gb")
    pull = f"ollama pull {rec_name}"
    host_env = (os.environ.get("OLLAMA_HOST") or "").strip()
    host_note = f"OLLAMA_HOST={host_env}" if host_env else "OLLAMA_HOST is not set, so the default is used"

    commands: list[str] = []
    selected: str | None = None
    extra: dict[str, Any] = {}

    if probed is None:
        if loopback and binary is None:
            state = "ollama_missing"
            commands = ["brew install ollama"]
            next_step = (
                f"Install Ollama from {install.get('url', 'https://ollama.com/download')}: on macOS install the app or run "
                f"`brew install ollama`; on Linux run `{install.get('linux', 'curl -fsSL https://ollama.com/install.sh | sh')}`. "
                f"{install.get('path_note', 'Open a new terminal or restart your agent so PATH picks it up.')} "
                "(If Ollama is already installed, a new terminal or an agent restart is what makes PATH see it.)"
            )
            extra["install"] = {
                "url": install.get("url"),
                "macos": list(install.get("macos") or []),
                "linux": install.get("linux"),
                "path_note": install.get("path_note"),
            }
        elif loopback:
            state = "server_unreachable"
            commands = ["ollama serve"]
            next_step = (
                f"Ollama is installed but its server is not reachable at {host} ({host_note}). Open the Ollama app, "
                "or run `ollama serve` in a terminal and leave it running, then run `taxclaw doctor` again."
            )
        else:
            state = "server_unreachable"
            next_step = (
                f"The Ollama server at {host} ({host_note}) is not reachable. Check that machine and the network, "
                "or unset OLLAMA_HOST to use Ollama on this machine, then run `taxclaw doctor` again."
            )
    elif not vision:
        state = "no_vision_model"
        commands = [pull]
        weak = f" Installed but text-only (cannot read documents): {', '.join(text_only)}." if text_only else ""
        size_s = f", an approx. {_fmt_gb(size)} GB download" if size else ""
        path_s = "" if binary else " (`ollama` is not on PATH in this environment; use a new terminal or the Ollama app.)"
        next_step = (
            f"Ollama is running at {host} but has no model that can read images.{weak} Recommended for this machine "
            f"({_fmt_gb(ram) + ' GB RAM' if ram else 'RAM unknown'}): {rec_name}{size_s}. When you are ready, run "
            f"`{pull}`. TaxClaw never downloads models for you.{path_s}"
        )
    else:
        wanted = cfg.local_model
        if _tag(wanted) in {_tag(v) for v in vision}:
            state = "ready"
            selected = wanted
            next_step = (
                f"Local is ready: TaxClaw reads documents with {wanted} via Ollama at {host}, on this machine. "
                "Ingest one with `taxclaw ingest /absolute/path/to/document.pdf --json`."
            )
        else:
            state = "model_not_selected"
            suggest = _suggest_installed(vision, bucket, known_weak)
            commands = [f"taxclaw use-local --model {suggest}"]
            next_step = (
                f"Ollama has vision model(s) installed ({', '.join(vision)}), but TaxClaw's local model is '{wanted}', "
                f"which is not one of them. Run `taxclaw use-local --model {suggest}`."
            )

    check_model = selected or rec_name
    warn_installed = state == "ready" or (probed is not None and _tag(check_model) in {_tag(v) for v in vision})
    warnings = _warnings(check_model, installed=warn_installed, ram=ram, free=free) if loopback else []

    return {
        "state": state,
        "state_label": STATE_LABELS[state],
        "ready": state == "ready",
        "model": selected,
        "ollama_host": host,
        "ollama_host_source": host_note,
        "ollama_binary": binary,
        "server_reachable": probed is not None,
        "vision_models": vision,
        "text_only_models": text_only,
        "recommended": {
            "model": rec_name,
            "installed": rec_installed,
            "approx_download_gb": size,
            "approx_download": f"approx. {_fmt_gb(size)} GB" if size else None,
            "pull_command": None if rec_installed else pull,
            "ram_bucket": bucket.get("label"),
        },
        "this_machine": {"ram_gb": ram, "free_disk_gb": free},
        "warnings": warnings,
        "next_step": next_step,
        "commands": commands,
        "never_automatic": "TaxClaw does not install Ollama or download models; run the commands yourself or ask your agent to, with your OK.",
        **extra,
    }


# ---------------------------------------------------------------------------
# Path 2: cloud with your own keys
# ---------------------------------------------------------------------------

SENDS = (
    "Full page images of every document you ingest. They carry names, Social Security numbers, income and account "
    "numbers. The provider's terms and privacy policy apply, not TaxClaw's, including what they log or keep."
)
SENDS_CLAIRIC_EXTRA = " Cloudflare Clairic also receives the PDF text layer."


def _measured_line(meas: dict[str, Any] | None) -> str:
    if not meas:
        return "not benchmarked"
    return (
        f"measured, synthetic benchmark: {meas.get('fields')} fields, {meas.get('exact_documents')} exact documents, "
        f"{meas.get('seconds_per_page')} s/page ({meas.get('basis')})"
    )


def _choice_name(provider_id: str) -> str:
    for name, (_b, _p, pid) in CLOUD_CHOICES.items():
        if pid == provider_id:
            return name
    return provider_id


def cloud_status(cfg: Config) -> dict[str, Any]:
    """Usable cloud providers (key present in this environment), best to worst. No network."""

    cat = _models.load_catalog()
    dcat = cat.get("doctor") or {}
    order = {e["provider"]: i for i, e in enumerate(dcat.get("cloud_order") or [])}
    by_id = {e["provider"]: e for e in (dcat.get("cloud_order") or [])}
    t2 = _models.tier2_cloud(cfg, live=False)
    specs = (cat.get("tier2_cloud") or {}).get("providers") or {}

    usable: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for p in sorted(t2["providers"], key=lambda x: order.get(x["provider"], len(order))):
        pid = p["provider"]
        meta = by_id.get(pid) or {}
        measured = meta.get("measured")
        name = _choice_name(pid)
        if not p["configured"]:
            all_req = bool((specs.get(pid) or {}).get("env_all_required"))
            missing.append({"provider": pid, "label": p.get("label"), "env": list(p["env_presence"]), "all_required": all_req})
            continue
        rec = p.get("recommended") or {}
        model = (measured or {}).get("model") or rec.get("balance")
        if name == "cloudflare_clairic":
            model = CLAIRIC_MODEL
            command = f"taxclaw use-cloud {name} --accept-privacy"
        elif model:
            command = f"taxclaw use-cloud {name} --model {model} --accept-privacy"
        else:
            command = f"taxclaw use-cloud {name} --model <vision model id from `taxclaw models`> --accept-privacy"
        usable.append(
            {
                "rank": len(usable) + 1,
                "provider": pid,
                "label": p.get("label"),
                "use_cloud_name": name,
                "backend": CLOUD_CHOICES.get(name, (p.get("backend"),))[0],
                "model": model,
                "evidence": _measured_line(measured),
                "measured": measured,
                "terms_url": meta.get("terms_url"),
                "switch_command": command,
                "key_presence": dict(p["env_presence"]),
            }
        )

    return {
        "usable": usable,
        "not_configured": missing,
        "openclaw_providers": [o["provider"] for o in t2.get("openclaw_providers") or []],
        "key_check": "presence only: key values are never read into this report",
        "what_is_sent": SENDS,
        "what_is_sent_clairic_extra": SENDS_CLAIRIC_EXTRA.strip(),
        "switching": (
            "TaxClaw never switches to cloud on its own. You switch with the command shown for a provider, which prints "
            "the privacy text and refuses unless you add --accept-privacy. The consent, its time and the provider are "
            "recorded in config. `taxclaw use-local` switches back."
        ),
        "ordering": "Best to worst by measured accuracy where the catalog has measurements; providers without measurements follow, in a fixed order, labelled not benchmarked.",
    }


def cloud_choice(name: str) -> tuple[str, str, str | None]:
    """Resolve a ``use-cloud`` name to (canonical name, backend, openai_compat preset)."""

    n = CLOUD_CHOICE_ALIASES.get(name.strip().lower(), name.strip().lower())
    if n not in CLOUD_CHOICES:
        raise ValueError(f"unknown cloud backend '{name}'. Choose one of: {', '.join(CLOUD_CHOICES)}")
    backend, preset, _pid = CLOUD_CHOICES[n]
    return n, backend, preset


def privacy_text(name: str, model: str | None) -> str:
    n, backend, _preset = cloud_choice(name)
    cat = _models.load_catalog()
    pid = CLOUD_CHOICES[n][2]
    label = ((cat.get("tier2_cloud") or {}).get("providers") or {}).get(pid, {}).get("label", n)
    terms = next((e.get("terms_url") for e in (cat.get("doctor") or {}).get("cloud_order") or [] if e["provider"] == pid), None)
    extra = SENDS_CLAIRIC_EXTRA if n == "cloudflare_clairic" else ""
    model_s = f", model {model}" if model else ""
    return (
        "PRIVACY NOTICE - read before you continue\n"
        f"You are about to send your tax documents to {label} ({backend}{model_s}).\n"
        f"What is sent: {SENDS}{extra}\n"
        f"Whose terms apply: {label}'s."
        + (f" See {terms}.\n" if terms else "\n")
        + "What TaxClaw records: your consent, the time and the provider name, in your TaxClaw config.\n"
        "Nothing is sent until you ingest a document. You can go back at any time with `taxclaw use-local`."
    )


def switch_to_cloud(cfg: Config, name: str, model: str | None) -> Config:
    """Apply a cloud choice and record consent on ``cfg`` (caller saves). Raises ValueError on bad input."""

    n, backend, preset = cloud_choice(name)
    cat = _models.load_catalog()
    if backend == "anthropic":
        if not model:
            conf = (((cat.get("tier2_cloud") or {}).get("providers") or {}).get("anthropic") or {}).get("confirmed") or {}
            model = conf.get("balance")
        if not model:
            raise ValueError("--model is required for anthropic")
        cfg.cloud_model = model
    elif backend == "openai_compat":
        if not model:
            raise ValueError(f"--model is required for {n}: pick a vision-capable model id (see `taxclaw models`)")
        cfg.openai_compat_provider = preset or "openai"
        cfg.openai_compat_model = model
        # The consent names the provider; make sure documents really go there, not to an older custom URL.
        cfg.openai_compat_base_url = ""
        cfg.openai_compat_api_key_env = ""
    else:
        if model and model != CLAIRIC_MODEL:
            raise ValueError("cloudflare_clairic uses a fixed model; do not pass --model")
    cfg.model_backend = backend
    record_cloud_consent(cfg)
    return cfg


def switch_to_local(cfg: Config, model: str | None) -> Config:
    cfg.model_backend = "local"
    if model:
        cfg.local_model = model.strip()
    clear_cloud_consent(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Path 3: hosted (coming soon)
# ---------------------------------------------------------------------------


def hosted_status() -> dict[str, Any]:
    h = _models.load_catalog().get("hosted") or {}
    enabled = bool(h.get("enabled"))
    name = h.get("name") or "TaxClaw Cloud"
    if not enabled:
        # No pricing anywhere until the flag is on.
        return {"enabled": False, "name": name, "status": "coming_soon", "message": h.get("coming_soon") or f"{name} (hosted) is coming soon."}
    pricing = h.get("pricing") or {}
    return {
        "enabled": True,
        "name": name,
        "status": "available",
        "message": f"{name} (hosted): {pricing.get('text', '')}".strip(),
        "pricing": pricing,
        "consent": "Using it sends documents to TaxClaw Cloud and needs the same explicit, recorded consent as any cloud path.",
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def current_status(cfg: Config, local: dict[str, Any]) -> dict[str, Any]:
    from .ai import ensure_backend_ready

    ready = False
    problem: str | None = None
    if not cfg.is_cloud:
        ready = bool(local["ready"])
        if not ready:
            problem = local["next_step"]
    else:
        try:
            ensure_backend_ready(cfg)  # cloud: privacy flag + key presence only, no network
            ready = True
        except Exception as e:  # noqa: BLE001
            problem = str(e)
    return {
        "backend": cfg.backend,
        "model": cfg.model_name(),
        "provider": cfg.provider_name(),
        "is_cloud": bool(cfg.is_cloud),
        "documents_left_machine": bool(cfg.is_cloud),
        "privacy_acknowledged": bool(cfg.privacy_acknowledged),
        "privacy_acknowledged_at": cfg.privacy_acknowledged_at or None,
        "consent_provider": cfg.cloud_provider or None,
        "ready": ready,
        "problem": problem,
    }


def build_report(cfg: Config | None = None) -> dict[str, Any]:
    """The doctor report. Read-only: no installs, downloads, config writes or provider calls."""

    cfg = cfg or load_config(create_dirs=False)
    local = local_status(cfg)
    cloud = cloud_status(cfg)
    hosted = hosted_status()
    cur = current_status(cfg, local)
    if cur["ready"]:
        if cfg.is_cloud:
            next_step = (
                f"Ready. Documents are being sent to {cur['provider']} ({cur['model']}) under the consent recorded "
                f"{cur['privacy_acknowledged_at'] or '(no timestamp recorded)'}. Switch back any time with `taxclaw use-local`."
            )
        else:
            next_step = local["next_step"]
    else:
        next_step = cur["problem"] or local["next_step"]
        if cfg.is_cloud and not cfg.privacy_acknowledged:
            next_step += " Only the user can give that consent: `taxclaw use-cloud <backend> --accept-privacy`, or `taxclaw use-local`."
    cat = _models.load_catalog()
    return {
        "doctor_version": DOCTOR_VERSION,
        "read_only": True,
        "ready": cur["ready"],
        "next_step": next_step,
        "current": cur,
        "local": local,
        "cloud": cloud,
        "hosted": hosted,
        "agent_rules": AGENT_RULES,
        "catalog": {"source": cat.get("source"), "as_of": cat.get("as_of")},
    }


def backend_next_step(cfg: Config | None = None) -> str:
    """One-line next step for error messages (ingest not ready)."""

    try:
        return build_report(cfg)["next_step"]
    except Exception:  # noqa: BLE001
        return "Run `taxclaw doctor` to see what to do next."


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


def _wrap(text: str, indent: str, width: int = 100) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent) or [indent.rstrip()]


def format_report(r: dict[str, Any]) -> str:
    cur, loc, cloud, hosted = r["current"], r["local"], r["cloud"], r["hosted"]
    L: list[str] = []
    L.append("TaxClaw doctor (read-only: it checks, and changes nothing)")
    L.append("")
    where = "on this machine" if not cur["is_cloud"] else f"by {cur['provider']}, OFF this machine"
    L.append(f"Now: documents are read {where} ({cur['backend']} / {cur['model'] or 'no model set'}).")
    if cur["is_cloud"]:
        L.append(f"     Cloud consent recorded: {cur['privacy_acknowledged_at'] or ('none' if not cur['privacy_acknowledged'] else 'yes, but no timestamp (older config)')}"
                 + (f" for {cur['consent_provider']}" if cur["consent_provider"] else ""))
    L.append(f"     Ready to ingest: {'yes' if r['ready'] else 'no'}")
    L.append("")
    L.append("PATH 1 - Local, on this machine (private: documents never leave it)")
    L.append(f"  Status: {loc['state_label']}")
    if loc["model"]:
        L.append(f"  Model: {loc['model']} (Ollama at {loc['ollama_host']})")
    elif loc["vision_models"]:
        L.append(f"  Vision models installed: {', '.join(loc['vision_models'])}")
    rec = loc["recommended"]
    if not loc["ready"]:
        size = f", {rec['approx_download']} download" if rec["approx_download"] else ""
        L.append(f"  Recommended for this machine: {rec['model']}{size}" + (" (already installed)" if rec["installed"] else ""))
    m = loc["this_machine"]
    ram_s = f"{m['ram_gb']:g} GB RAM" if m["ram_gb"] else "RAM unknown"
    disk_s = f", {m['free_disk_gb']:g} GB free disk" if m["free_disk_gb"] is not None else ""
    L.append(f"  This machine: {ram_s}{disk_s}")
    for w in loc["warnings"]:
        L.extend(_wrap("WARNING: " + w, "  "))
    L.extend(_wrap("Next step: " + loc["next_step"], "  "))
    L.append("")
    L.append("PATH 2 - Cloud with your own API keys (documents LEAVE this machine)")
    if cloud["usable"]:
        L.append("  Usable providers found in this environment (key presence only), best to worst:")
        for p in cloud["usable"]:
            L.append(f"   {p['rank']}. {p['label']} - {p['model'] or 'choose a model'} - {p['evidence']}")
            L.append(f"      switch: {p['switch_command']}")
            if p.get("terms_url"):
                L.append(f"      their terms apply: {p['terms_url']}")
    else:
        L.append("  No cloud API keys found in this environment (checked by presence only).")
        names = "; ".join(f"{p['label']} ({(' + ' if p.get('all_required') else ' or ').join(p['env'])})" for p in cloud["not_configured"])
        L.extend(_wrap(f"Supported: {names}. Set the key in the environment TaxClaw runs in, then run `taxclaw doctor` again.", "  "))
    if cloud["openclaw_providers"]:
        L.extend(_wrap(f"Also configured in OpenClaw (names only): {', '.join(cloud['openclaw_providers'])}. Export the key to TaxClaw's environment to use it.", "  "))
    L.extend(_wrap("What would be sent: " + cloud["what_is_sent"], "  "))
    L.extend(_wrap("Switching: " + cloud["switching"], "  "))
    L.append("")
    L.append("PATH 3 - TaxClaw Cloud (hosted)")
    L.extend(_wrap(hosted["message"], "  "))
    if hosted.get("consent"):
        L.extend(_wrap(hosted["consent"], "  "))
    L.append("")
    L.append("Which path do you want? Nothing is installed, downloaded or sent until you choose and run it.")
    L.append(f"Models and measurements: {r['catalog']['source']} (as of {r['catalog']['as_of']})")
    return "\n".join(L) + "\n"
