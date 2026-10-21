# Synthetic extraction benchmark

This is a **clean-form smoke benchmark**, not a claim of real-world tax-document
accuracy. All names, identifiers and financial figures are invented. No personal
documents or credentials belong in this directory. It does not calculate or file
taxes. Websites are outside this work package.

The original 12-form results in `results/2026-10-20/` are **historical**: they
measure the pre-upgrade application at `79cf4c3`. They are not current-main scores.
The subsequent changed-form corpus and run below use the merged `87efee5` source.

## Corpus

`fixtures.py` deterministically builds 12 documents / 14 pages: W-2, 1099-NEC,
1099-INT, 1099-DIV, consolidated-1099, 1099-B, 1099-MISC, 1099-OID, K-1,
1099-DA, 1099-R and 1040. K-1 and 1099-DA each have two pages. PDFs use numbered
human labels, two columns and a prominent `SYNTHETIC NOT FOR FILING` mark.

The separate manifest contains 233 expected leaf fields, their types, and relative
PDF paths. Coverage includes explicit zero, blank, negative amount, masked ID,
leading zero, coded object, boolean and multi-transaction output. Expected values
are **never included in model prompts or PDF metadata**. The model receives only
the rendered image and TaxClaw's existing extraction prompt.

These are simplified layouts, not official IRS facsimiles. There is one clean
example per type, no held-out population, repeated trials, scan damage, handwriting,
unseen brokerage layouts or scanned-document classification. Do not generalize
these results to customer documents. Add varied/scan-only examples and validation
before making broader claims or charging for an accuracy promise.

## Targeted post-upgrade corpus

`followup_fixtures.py` provides a separate, versioned corpus for 1099-R, 1099-G,
1099-K and K-1. Each form has a clean and an image-only degraded-scan variant.
The expected keys follow the merged schemas, including `distribution_codes` and
K-1's `13W`-style code keys. Original fixtures and answer keys are not rewritten.
Rasterization/degradation parameters are stored in the new manifest. Scanned
versions contain no text layer, exercising vision classification as well as
extraction. This remains a small synthetic test, not a representative scan study.

```bash
python -m benchmarks.taxclaw_accuracy.runner build \
  --corpus changed-forms --output .benchmark/changed-forms
python -m benchmarks.taxclaw_accuracy.runner run \
  --fixtures .benchmark/changed-forms --output .benchmark/changed-local \
  --transport app --host http://127.0.0.1:11434 \
  --types 1099-R 1099-G 1099-K K-1 \
  --models gemma3:4b gemma3:12b gemma4:latest qwen3.5:4b glm-ocr:latest
```

Use `--variants clean` or `--variants degraded_scan` to select one variant. The
summary keeps clean and degraded results separate; it does not overwrite one
with the other. Run the same selected corpus through `claude-subscription` for
the bounded Haiku comparator, using the wrapper syntax below.

## Run

From the repository root, in a Python environment with the application's extraction
dependencies installed (`pymupdf`, `ollama`, `anthropic`, `pyyaml`):

```bash
python -m unittest benchmarks.taxclaw_accuracy.test_grader -v
python -m benchmarks.taxclaw_accuracy.runner build --output .benchmark/fixtures
python -m benchmarks.taxclaw_accuracy.runner run \
  --fixtures .benchmark/fixtures --output .benchmark/local-app \
  --transport app --host http://127.0.0.1:11434 \
  --models gemma3:12b gemma3:4b qwen3.5:4b glm-ocr:latest gemma4:latest
python -m benchmarks.taxclaw_accuracy.runner regrade \
  --fixtures .benchmark/fixtures --output .benchmark/local-app
```

Models run serially to avoid competing for the reference machine's memory. The
runner never downloads a model or substitutes another one. Use a new output
directory if the application, harness, fixtures, transport, model digests, host or
requested configuration change. Resume skips already recorded model/document
pairs, including failures; reruns belong in a new directory. A timeout/error is a
failed document and earns no field credit, not an omitted observation.

`app` runs the actual `src.extract.extract_document` / `src.ai` / backend code with an
explicit Ollama client endpoint and request timeout; it does not add structured
output beyond what the application itself sends, or modify model parameters.
On current main the application sends its per-form JSON schema; raw page records
preserve that request format. Classification is scored separately. Extraction
uses the known document type to isolate extraction accuracy, so this is **not**
an end-to-end ingest/CLI benchmark.

`ollama-json` is a separately labeled experiment using the same application
rendering, prompt and page-merging code, but adds Ollama `format="json"` and a
2048-token prediction limit. Never combine its scores with `app` results or call
it production verification before the application's corresponding change ships.

Haiku uses an explicitly supplied, subscription-authenticated Claude wrapper:

```bash
python -m benchmarks.taxclaw_accuracy.runner run \
  --fixtures .benchmark/fixtures --output .benchmark/haiku \
  --transport claude-subscription --models claude-haiku-5-5 \
  --claude-wrapper /absolute/path/to/claude-subscription
```

This sends image content on stdin; all CLI tools, MCP servers and skills are
disabled. It checks the CLI's reported model identity. The wrapper is supplied by
the operator and must use subscription/OAuth authentication. It is **not** the
application's Anthropic SDK/API transport, and its timings include CLI startup and
subscription infrastructure. Do not infer hosted API cost or server latency from
these measurements. No Claude API key is used or required by this benchmark.

Clairic is not implemented or measured by this harness yet; it remains a separate
provider-integration and credential prerequisite. Do not publish an inferred score.

## Scoring and evidence

Money uses exact decimal equality (formatting differences such as commas and
parenthesized negatives are normalized), not floating-point tolerance. Text is
case/whitespace normalized. IDs preserve leading zeroes and masks; dates accept
ISO and US formatting. Booleans must be JSON booleans. Missing, blank, zero and
null are distinct. Object/array structure is checked. Transaction order and count
must match; extra fields/rows prevent an exact-document pass.

Each result includes correct/expected fields, populated-field and blank-field
counts, unexpected fields, container-shape errors and per-field differences.
Both raw extraction and exact-document outcomes matter: many correct blanks must
not hide wrong income values. Canonical code-key mismatches (for example `13W`
versus `W`) are reported as contract mismatches, not automatically described as
OCR/value errors. Existing prompts leave some code-key conventions ambiguous.

The suggested strict smoke gate is **all 12 types: dedicated schema, correct
classification, zero runtime errors, and an exact document match**. Passing one
example per type is necessary for this smoke gate, not sufficient evidence for
production accuracy or the entire 1.0 release. No model recommendation should
silently waive unsupported form types.

Output includes `metadata.json`, immutable `results.jsonl`, and `summary.json`.
Metadata records source hashes, fixture hashes, package versions, requested models,
available model digests, transport and configuration. Raw page responses preserve
model-reported identity and timings. Ollama resident-model snapshots make runner/
digest selection inspectable when duplicate tags exist.

`regrade` preserves raw inference records, writes `scored-results.jsonl` plus
`scoring.json`, and regenerates the summary. Its receipt binds the raw records,
manifest and grader hashes and rechecks recorded model identity. Regrading
changes evaluation only; it is not a new inference trial. If additional raw
records appear, regrade again before summarizing.

Seconds/page means document extraction wall time divided by document page count,
including rendering, network and model load, excluding classification. First-use
and warm-page timings are retained; no attempt is made to claim pure model speed
or statistically significant rankings from this single pass.


## Completed evidence and release interpretation (2026-10-20)

- [Original 12-type baseline](results/2026-10-20/RESULTS.md): 84 preserved records, measured before the dependency/schema upgrades. Historical only.
- [Changed-form follow-up](results/2026-10-20-main-87efee5/RESULTS.md): all 48 requested evaluations completed, covering R/G/K/K-1 clean and degraded scans on application main `87efee5`, with source freeze `800b761`. Independent parent verification rederived every score from raw responses and verified archived evidence, source and fixture hashes.
- Later main `a47c572` leaves the tested extraction functions/dependencies unchanged; its separate capital-lot/export path was not benchmarked here.

Haiku subscription CLI matched 224/224 fields and 8/8 documents exactly (5.21 extraction seconds/page). The strongest observed local aggregate was Gemma3:12b, 176/224 fields (78.57%), with no exact documents and 65.95 seconds/page. Gemma3:4b was 158/224 (70.54%) at 18.88 seconds/page. GLM-OCR now parses but misclassified both K-1 variants; Qwen had five failed extractions. These are tag observations on one host, not a general model ranking.

**Release recommendation:** the benchmark execution is complete. These results support positioning TaxClaw as assisted document extraction requiring a person to verify every extracted value; they do not support unattended filing, guaranteed accuracy, or automatic acceptance based on a model confidence score. Pip owns the version/release decision. Haiku's production API path and Clairic were not verified by this suite. A small synthetic grid corpus cannot establish representative real-document accuracy.

Two reporting defects found during the run are fixed for future executions: summaries now identify actual variants, and regrading preserves a transport error when no model response arrived instead of calling it a model-identity mismatch. Historical artifacts remain immutable and explain their original labels; the numeric scores are unaffected.

## Full current-main gate (533760d)

[Full clean/degraded current-main evidence](results/2026-10-20-main-533760d/RESULTS.md) includes all 13 README-supported information-form types plus best-effort 1040. The clarified release gate covers the supported 13 only; 1040 is reported separately, with an original-12 comparison retained. The strict scorer is unchanged. Haiku subscription inference is complete; local-model inference is pending in that evidence directory.

## Fresh tax-year-fix gate (b2c4f4c)

[Fresh Haiku supported-13 evidence](results/2026-10-21-main-b2c4f4c/RESULTS.md):
clean **281/281 fields, 13/13 exact**; degraded **281/281, 13/13 exact**.
All 26 classifications correct; zero runtime failures. Same strict scorer and
fixtures; new subscription Haiku inference against exactly b2c4f4c, independently
replayed and rescored. This supersedes the prior Haiku gate outcome for that
revision only. No fresh 1040 or local-model result, production API verification,
or release authorization is implied.
