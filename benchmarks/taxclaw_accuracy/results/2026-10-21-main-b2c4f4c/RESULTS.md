# Fresh Haiku supported-13 gate — PASS

Fresh inference on 2026-10-21 against application revision
`b2c4f4ca95946178f2805bec915e549020f0336b` (merged tax-year fix, PR #12).
This is a new model run, not a regrade of historical Haiku responses.

- Clean: **281/281 fields; 13/13 exact documents**.
- Degraded scans: **281/281 fields; 13/13 exact documents**.
- Combined: **562/562 fields; 26/26 exact documents; 26/26 classifications correct**.
- Zero runtime errors; all 13 supported types have dedicated schemas.
- The three previously failing cases (MISC clean, B degraded, consolidated-1099 degraded) are exact in this fresh run.
- Extraction wall time: 4.79 seconds/page overall; includes CLI startup and rendering, excludes classification.

## Scope and interpretation

The clarified gate covers 13 supported information-form types, each clean and
degraded: 26 documents / 30 pages. Best-effort 1040 was not rerun and is excluded;
its prior result is unchanged historical evidence, not a current measurement.
No local-model result is included in this report.

The strict scorer, runner, fixture generator, manifest, and PDF bytes are unchanged
from the prior full gate. The scorer SHA-256 remains
`39227b5ccffac57639e110a3e6d9502803af444d88336780ac5c8ebab7e6b28b`.
The application and requirements byte-match b2c4f4c. The benchmark-only harness was
committed at `00a197a2cf1a2c458c0f434fddc797e2f44ec180` before inference.
Main has advanced since the request; no later application revision was substituted.

Exact requested and observed model: `claude-haiku-5-5`. The subscription image
adapter and wrapper hash match the earlier run. Tools, MCP, skills, and CLI session
persistence are disabled for inference. This is **not verification of the
production Anthropic SDK/API transport or hosted cost**.

All fresh raw year values already satisfy the new prompt contract; the replay
observed zero year-type conversions. This pass verifies the current overall path,
not an additional observed coercion event. The tax-year unit tests exercise
coercion and invalid-year review separately.

This small synthetic smoke gate passes. It does not establish representative
customer-document accuracy or authorize release, tagging, publishing, or deployment.
Pip owns the release PR update; Doug retains the 1.0.0 go decision.

## Verification and reproducibility

All 26 records were independently rescored. Every successful raw page response
was replayed offline through the actual b2c4f4c extraction/merge/finalization code,
checking rendered-image and prompt hashes, final data equality, model identities,
fixture hashes, matrix completeness, and source hashes. See `verification.json`,
`freeze.json`, `gate-report.json`, and `haiku-subscription/` for bound evidence.

40 focused tests passed: strict scorer, runner, full/changed fixtures, and tax-year
contract. Compileall and diff checks passed. No application source was edited.

From repository root, with the pinned extraction dependencies installed:

```bash
python -m benchmarks.taxclaw_accuracy.full_fixtures .benchmark/full-b2c4f4c
python -m benchmarks.taxclaw_accuracy.runner regrade --fixtures .benchmark/full-b2c4f4c --output benchmarks/taxclaw_accuracy/results/2026-10-21-main-b2c4f4c/haiku-subscription
PYTHONPATH=. python benchmarks/taxclaw_accuracy/results/2026-10-21-main-b2c4f4c/verify_evidence.py --fixtures .benchmark/full-b2c4f4c
PYTHONPATH=. python benchmarks/taxclaw_accuracy/results/2026-10-21-main-b2c4f4c/build_gate_report.py
```

Replay/regrading is offline and does not call the model again. Inference options
and all pinned inputs are preserved in `haiku-subscription/metadata.json`.
