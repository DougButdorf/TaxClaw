# Changelog

## 0.1.2 - 2026-05-20

- Fixed setup on machines where `python3` is older than TaxClaw's current dependencies require by selecting Python 3.10+ when available and adding a clear failure message.
- Fixed POST/DELETE localhost checks so alternate local ports configured with `TAXCLAW_PORT` or config do not break forms.
- Made `start.sh` respect the configured port when `TAXCLAW_PORT` is not set.
- Aligned upload limits with `max_upload_bytes` from config and made browser upload MIME checks match the backend's supported PDF/image types.
- Corrected the OpenClaw skill documentation to use `privacy_acknowledged`, matching the actual config key.
- Made smoke tests use an isolated temporary home directory so verification does not touch a user's real TaxClaw config or data.
