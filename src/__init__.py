# taxclaw

# Single source of truth for the release version. The FastAPI app, export
# metadata, MCP server, CLI `--version` and setup output import it; SKILL.md
# (metadata.version) and RUNBOOK.md are checked against it by the unit tests.
__version__ = "1.0.0"
