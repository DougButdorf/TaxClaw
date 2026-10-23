# Full current-main gate — 533760d

**Haiku strict supported-13 gate: FAIL.** Local-model inference is pending and will be added to this PR. The 13 supported types are the gate; 1040 is best-effort and does not block it (Pip scope clarification). No scorer relaxation.

## Haiku 5.5 — frozen subscription adapter

| View | Clean fields | Clean exact | Degraded fields | Degraded exact |
|---|---:|---:|---:|---:|
| Supported 13 (release gate) | 280/281 | 12/13 | 279/281 | 11/13 |
| 1040 alone, best-effort | 0/19 | 0/1 | 0/19 | 0/1 |
| Original 12, comparison only | 236/256 | 10/12 | 235/256 | 9/12 |

Supported forms: W-2; 1099-NEC, INT, DIV, B, MISC, OID, R, G, K, DA; K-1; consolidated-1099. All 26 supported-form classifications were correct; zero runtime errors. Across all 14 types: 28 documents / 32 pages, 559/600 fields, 23/28 exact, 28/28 classifications, zero runtime errors.

### Exact failing supported case IDs

- `full_gate_1099_misc_clean`
- `full_gate_1099_b_degraded_scan`
- `full_gate_consolidated_1099_degraded_scan`

Each has exactly one mismatch: `tax_year` is JSON number `2025` rather than string `"2025"`. This is a real output-contract failure, **not** an incorrectly read printed year. There were no other wrong supported fields, extra fields, or shape errors. The scorer preserves this distinction. Do not revise these raw records or label this pass as a gate success. A future application normalization fix can be assessed separately against preserved raw page outputs; that is not new inference and must bind its own source and scoring receipt.

1040 returned the generic extraction structure and matched none of its 19 canonical fields in either variant; it is deliberately not part of the supported-13 gate. The original-12 view retains it only for historical comparison. Original R and K-1 fixtures use the corrected follow-up contracts, so this is not a paired statistical comparison with the older pre-fix corpus.

## Freeze and reproducibility

- Application: `533760d94d43bd7c93bf10e09e3f5f84eb55e510`. All 18 Python source files plus requirements verified byte-identical to that commit before inference.
- Harness freeze: `c5f8b6f`; grader SHA-256 remains `39227b5ccffac57639e110a3e6d9502803af444d88336780ac5c8ebab7e6b28b`.
- Haiku wrapper SHA-256 matches the earlier frozen setup: `a47bc8ebb817bc01318aea24aeea46220d441f160e634c7d070d1f363dceb622`. Exact model `claude-haiku-5-5`, tools/MCP/skills disabled, 90-second per-call timeout, 2x application rendering. No API-key billing.
- New `full_fixtures.py` preserves all original types, replaces R/K-1 with corrected follow-up fixtures, adds G/K, and generates deterministic clean/image-only scan pairs: 28 documents / 32 pages per model. Clean/scan expected values are identical. Source/scan settings and all PDF hashes are bound by the manifest and run metadata.
- Haiku's subscription adapter is **not** the production Anthropic API transport. It does not verify hosted API latency, billing, or economics.
- Local models run serially on the same reference Mac host using the real application Ollama path (no extra JSON-format experiment), timeout 180 seconds, requested order gemma3:12b then gemma3:4b. Duplicate tag digests and actual resident-model evidence are retained.
- Classification is measured separately; extraction uses the known document type. This is **not** an end-to-end ingest benchmark, real customer-document study, or guarantee of accuracy.

Generate the fixture PDFs locally (they are not retained in Git):

```bash
python -m benchmarks.taxclaw_accuracy.full_fixtures .benchmark/full-533760d
python -m benchmarks.taxclaw_accuracy.runner regrade --fixtures .benchmark/full-533760d --output benchmarks/taxclaw_accuracy/results/2026-10-20-main-533760d/haiku-subscription
python -m benchmarks.taxclaw_accuracy.gate_report --root benchmarks/taxclaw_accuracy/results/2026-10-20-main-533760d --runs haiku-subscription
PYTHONPATH=. python benchmarks/taxclaw_accuracy/results/2026-10-20-main-533760d/release_views.py --runs haiku-subscription
PYTHONPATH=. python benchmarks/taxclaw_accuracy/results/2026-10-20-main-533760d/verify_evidence.py --fixtures .benchmark/full-533760d --runs haiku-subscription
```

`release-views.json` is the clarified supported-13 gate, 1040-only and original-12 comparison. `gate-report.json` preserves broader original-12/all-14 diagnostics; those populations are not the release gate. `parent-verification.json` binds all raw/scored data and both reports. Parent verification reconstructs actual extraction from raw model page responses, recomputes every field score, checks manifest-bound populations, source/fixture hashes and exact response model identities. `freeze.json` captures pre-inference provenance. Raw/scored JSONL are immutable evidence; local records will be added separately.

## Release interpretation

Under Pip's stated release rule, current evidence supports **0.2.0, not 1.0.0**. A production output-normalization fix requires its own verified evidence; the benchmark scorer must not be weakened. Local models remain assisted extraction: a person must verify every value. Public ClawHub publish, merge and release are not authorized by this evidence PR.
