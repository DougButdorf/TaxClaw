# AGENTS.md

## GBRAIN

Before meaningful coding, research, audit, config, document, or multi-step operational work, query GBRAIN for a narrow slice of relevant prior context. Use the `gbrain` MCP server when available; otherwise use the CLI fallback:

```bash
gbrain query "<project or repo> <task> decisions blockers artifacts" --source-id __all__ --no-expand
```

Read only the strongest returned pages before relying on them. Treat GBRAIN as context, not authority: current user instructions, live systems, source files, and official docs win when they conflict.

After meaningful work, capture durable artifacts and decisions back to GBRAIN under the producing source (`codex`, `claude`, or `openclaw`). Include changed files, commits, deployments, cron IDs, test results, blockers, and reusable lessons. Do not store secrets, raw credentials, login codes, or noisy scratch logs.
