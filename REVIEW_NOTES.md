# TaxClaw Refresh Notes - 2026-05-20

Reviewed scope:

- OpenClaw skill manifest and install/run docs.
- Setup/runtime scripts, CLI entrypoints, dependency install path, and smoke test.
- FastAPI startup, upload flow, localhost protections, settings/privacy acknowledgment, export routes, and storage path handling.
- Requirements pins against the local macOS/OpenClaw environment.
- Basic secret-risk scan across tracked source/doc files.

Changes made:

- Version bumped to 0.1.2 in the skill manifest, FastAPI app, exporter metadata, and docs.
- Setup now selects Python 3.10+ instead of blindly using `python3`; this fixes installs on macOS machines where `python3` is Apple Python 3.9 while current PyMuPDF requires Python 3.10+.
- Localhost form protections now allow any loopback port, keeping CSRF/host checks intact while supporting `TAXCLAW_PORT` and non-default config ports.
- `start.sh` now reads the configured port when `TAXCLAW_PORT` is unset.
- Upload preflight now honors `max_upload_bytes` from config and accepts the same PDF/image MIME types that backend storage supports.
- `scripts/smoke.sh` now uses a temporary `HOME`, avoiding writes to real `~/.config/taxclaw` and `~/.local/share/taxclaw` during verification.
- Skill docs now reference the correct `privacy_acknowledged` config key.

Verification:

```bash
./scripts/smoke.sh
venv/bin/python -m compileall src
FastAPI TestClient POST to /settings on an alternate loopback port
./start.sh on configured port 8423, verified with curl, then stopped
rg -n "<common token/private-key/API-key patterns>" . -g '!venv/**' -g '!.git/**'
```

Remaining risks:

- End-to-end extraction accuracy still depends on installed local vision models or a user-provided Anthropic API key; no live model extraction was run in this refresh.
- The app is intentionally localhost-only and stores sensitive tax documents locally; users should keep the TaxClaw data directory protected and avoid exposing the port outside loopback.
