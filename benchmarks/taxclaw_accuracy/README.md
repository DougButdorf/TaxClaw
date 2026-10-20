# Synthetic extraction benchmark

This is a **clean-form smoke benchmark**, not a claim of real-world tax-document
accuracy. All names, identifiers and financial figures are invented. No personal
documents or credentials belong in this directory. It does not calculate or file
taxes. Websites are outside this work package.

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

`app` runs the actual `src.extract.extract_document` / `src.ai` code with an
explicit Ollama client endpoint and request timeout; it does not add structured
output or modify model parameters. Classification is scored separately. Extraction
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
