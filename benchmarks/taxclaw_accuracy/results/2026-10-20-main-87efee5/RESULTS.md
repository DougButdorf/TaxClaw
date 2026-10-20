# Current-main changed-form synthetic benchmark

Application main `87efee5`, benchmark/source freeze `800b761`. **48/48 requested documents completed:** five local tags × eight documents, plus eight Haiku subscription-CLI documents. No release approval or real-world accuracy claim.

## Results

| Model/tag | Clean fields | Scan fields | Exact docs | Extraction errors | Classification | Extraction s/page |
|---|---:|---:|---:|---:|---:|---:|
| gemma3:4b | 75/112 | 83/112 | 0/8 | 0 | 8/8 | 18.88 |
| gemma3:12b | 90/112 | 86/112 | 0/8 | 0 | 8/8 | 65.95 |
| gemma4:latest | 59/112 | 97/112 | 0/8 | 1 | 8/8 | 75.42 |
| qwen3.5:4b | 44/112 | 26/112 | 3/8 | 5 | 8/8 | 48.41 |
| glm-ocr:latest | 80/112 | 78/112 | 0/8 | 0 | 6/8 | 11.75 |
| claude-haiku-5-5 | 112/112 | 112/112 | 8/8 | 0 | 8/8 | 5.21 |

Haiku: 112/112 fields and 4/4 exact documents per variant; 224/224 fields, 8/8 exact overall. This tests subscription CLI only, not the production API integration or privacy controls.

## Per-form detail

| Model/tag | Form | Variant | Fields | Exact | Status | Classification correct | Extraction s/page |
|---|---|---|---:|---|---|---|---:|
| gemma3:4b | 1099-R | clean | 23/30 | False | ok | True | 21.71 |
| gemma3:4b | 1099-R | degraded_scan | 26/30 | False | ok | True | 22.93 |
| gemma3:4b | 1099-G | clean | 11/18 | False | ok | True | 11.79 |
| gemma3:4b | 1099-G | degraded_scan | 12/18 | False | ok | True | 12.24 |
| gemma3:4b | 1099-K | clean | 21/26 | False | ok | True | 15.33 |
| gemma3:4b | 1099-K | degraded_scan | 23/26 | False | ok | True | 15.67 |
| gemma3:4b | K-1 | clean | 20/38 | False | ok | True | 18.61 |
| gemma3:4b | K-1 | degraded_scan | 22/38 | False | ok | True | 25.93 |
| gemma3:12b | 1099-R | clean | 24/30 | False | ok | True | 67.75 |
| gemma3:12b | 1099-R | degraded_scan | 24/30 | False | ok | True | 71.24 |
| gemma3:12b | 1099-G | clean | 17/18 | False | ok | True | 54.23 |
| gemma3:12b | 1099-G | degraded_scan | 14/18 | False | ok | True | 73.12 |
| gemma3:12b | 1099-K | clean | 25/26 | False | ok | True | 71.01 |
| gemma3:12b | 1099-K | degraded_scan | 24/26 | False | ok | True | 62.63 |
| gemma3:12b | K-1 | clean | 24/38 | False | ok | True | 75.82 |
| gemma3:12b | K-1 | degraded_scan | 24/38 | False | ok | True | 53.95 |
| gemma4:latest | 1099-R | clean | 25/30 | False | ok | True | 87.71 |
| gemma4:latest | 1099-R | degraded_scan | 26/30 | False | ok | True | 70.54 |
| gemma4:latest | 1099-G | clean | 15/18 | False | ok | True | 43.29 |
| gemma4:latest | 1099-G | degraded_scan | 15/18 | False | ok | True | 50.30 |
| gemma4:latest | 1099-K | clean | 19/26 | False | ok | True | 94.54 |
| gemma4:latest | 1099-K | degraded_scan | 25/26 | False | ok | True | 59.94 |
| gemma4:latest | K-1 | clean | 0/38 | False | error | True | 90.09 |
| gemma4:latest | K-1 | degraded_scan | 31/38 | False | ok | True | 83.87 |
| qwen3.5:4b | 1099-R | clean | 0/30 | False | error | True | 74.82 |
| qwen3.5:4b | 1099-R | degraded_scan | 0/30 | False | error | True | 68.67 |
| qwen3.5:4b | 1099-G | clean | 18/18 | True | ok | True | 40.75 |
| qwen3.5:4b | 1099-G | degraded_scan | 0/18 | False | error | True | 75.26 |
| qwen3.5:4b | 1099-K | clean | 26/26 | True | ok | True | 49.69 |
| qwen3.5:4b | 1099-K | degraded_scan | 26/26 | True | ok | True | 50.20 |
| qwen3.5:4b | K-1 | clean | 0/38 | False | error | True | 30.80 |
| qwen3.5:4b | K-1 | degraded_scan | 0/38 | False | error | True | 31.55 |
| glm-ocr:latest | 1099-R | clean | 27/30 | False | ok | True | 20.48 |
| glm-ocr:latest | 1099-R | degraded_scan | 27/30 | False | ok | True | 8.44 |
| glm-ocr:latest | 1099-G | clean | 17/18 | False | ok | True | 13.10 |
| glm-ocr:latest | 1099-G | degraded_scan | 17/18 | False | ok | True | 4.63 |
| glm-ocr:latest | 1099-K | clean | 21/26 | False | ok | True | 15.01 |
| glm-ocr:latest | 1099-K | degraded_scan | 19/26 | False | ok | True | 6.51 |
| glm-ocr:latest | K-1 | clean | 15/38 | False | ok | False | 10.56 |
| glm-ocr:latest | K-1 | degraded_scan | 15/38 | False | ok | False | 14.11 |
| claude-haiku-5-5 | 1099-R | clean | 30/30 | True | ok | True | 5.91 |
| claude-haiku-5-5 | 1099-R | degraded_scan | 30/30 | True | ok | True | 3.60 |
| claude-haiku-5-5 | 1099-G | clean | 18/18 | True | ok | True | 4.04 |
| claude-haiku-5-5 | 1099-G | degraded_scan | 18/18 | True | ok | True | 4.83 |
| claude-haiku-5-5 | 1099-K | clean | 26/26 | True | ok | True | 3.05 |
| claude-haiku-5-5 | 1099-K | degraded_scan | 26/26 | True | ok | True | 4.91 |
| claude-haiku-5-5 | K-1 | clean | 38/38 | True | ok | True | 6.55 |
| claude-haiku-5-5 | K-1 | degraded_scan | 38/38 | True | ok | True | 6.35 |

## Errors and representative misses

All 8 extraction/classification error or classification-mismatch records are in `errors.json`; every incorrect field, extra key and shape mismatch is in `field-errors.json`. Raw/scored evidence is preserved, with no aliases, silent repairs, or failed-call blank credit.

- gemma4:latest / wp_f_changed_k_1_clean: LocalModelError: Ollama is not reachable at http://100.125.33.53:11434. Start it with `ollama serve` (or open the Ollama app), check OLLAMA_HOST if Ollama runs elsewhere, or switch TaxClaw to cloud mode in Settings.
- qwen3.5:4b / wp_f_changed_1099_r_clean: ValueError: model returned an empty response (expected JSON)
- qwen3.5:4b / wp_f_changed_1099_r_degraded_scan: ValueError: model response was not valid JSON (Unterminated string starting at); response began: '{   "payer_name": "Juniper Example Works LLC",   "payer_tin": "00-XXX0000",   "recipient_name": "Morgan Sample",   "recipient_tin": "XXX-XX-0000",   "account_number": "SYN-0042",   "tax_year": "2025",'
- qwen3.5:4b / wp_f_changed_1099_g_degraded_scan: ValueError: model returned an empty response (expected JSON)
- qwen3.5:4b / wp_f_changed_k_1_clean: ValueError: model returned an empty response (expected JSON)
- qwen3.5:4b / wp_f_changed_k_1_degraded_scan: ValueError: model returned an empty response (expected JSON)
- glm-ocr:latest / wp_f_changed_k_1_clean: classification {'doc_type': '1099-DIV', 'confidence': 0.5, 'method': 'vision'}
- glm-ocr:latest / wp_f_changed_k_1_degraded_scan: classification {'doc_type': '1099-DIV', 'confidence': 0.5, 'method': 'vision'}

Regrading caveat: the one Gemma4 clean K-1 extraction attempt returned no provider response after 180.11 seconds. Raw evidence records the quoted local reachability error; the frozen regrader relabels the missing response model identity as `Recorded provider model does not match requested model`. Both messages are preserved (`raw_error` versus `error` in `errors.json`), and the failed document stays 0/38. This is not evidence of a substituted model: every actual observed response identity matched the requested tag. No upstream raw/scored file was edited to conceal this limitation.

Representative field misses (expected → actual; `None` means null, missing distinguished in machine evidence):

- gemma3:4b, 1099-R clean, `payer_tin`: `00-XXX0000` → `00-XX0000` (present=True).
- gemma3:4b, 1099-R clean, `recipient_tin`: `XXX-XX-0000` → `None` (present=True).
- gemma3:4b, 1099-R clean, `capital_gain`: `None` → `1850.00` (present=True).
- gemma3:4b, 1099-R clean, `distribution_codes`: `7Q` → `70` (present=True).
- gemma3:4b, 1099-R clean, `state_payer_number`: `NY QO-001908` → `NY Q0-001908` (present=True).
- gemma3:4b, K-1 clean: shape mismatches ['amt_items', 'distributions', 'foreign_transactions', 'other_credits', 'tax_exempt_and_nondeductible']; extra keys ['amt_items', 'distributions', 'foreign_transactions', 'other_credits', 'other_deductions.13', 'other_income.11', 'other_information.20', 'tax_exempt_and_nondeductible'].
- gemma3:12b, 1099-R clean, `payer_tin`: `00-XXX0000` → `00-XXXX000` (present=True).
- gemma3:12b, 1099-R clean, `taxable_amount_not_determined`: `False` → `None` (present=True).
- gemma3:12b, 1099-R clean, `total_distribution`: `False` → `None` (present=True).
- gemma3:12b, 1099-R clean, `distribution_codes`: `7Q` → `70` (present=True).
- gemma3:12b, 1099-R clean, `local_withheld`: `None` → `0.00` (present=True).
- gemma3:12b, K-1 clean: shape mismatches ['amt_items', 'distributions', 'foreign_transactions', 'other_credits', 'tax_exempt_and_nondeductible']; extra keys ['amt_items', 'distributions', 'foreign_transactions', 'other_credits', 'other_deductions.13G', 'other_deductions.14', 'other_deductions.15', 'other_deductions.16', 'other_deductions.17', 'other_deductions.18', 'other_deductions.19', 'other_deductions.20', 'other_deductions.87.65', 'other_information.127.90', 'tax_exempt_and_nondeductible'].
- gemma4:latest, 1099-R clean, `payer_tin`: `00-XXX0000` → `XXX-XX-0000` (present=True).
- gemma4:latest, 1099-R clean, `recipient_tin`: `XXX-XX-0000` → `None` (present=True).
- gemma4:latest, 1099-R clean, `capital_gain`: `None` → `1850.00` (present=True).
- gemma4:latest, 1099-R clean, `local_withheld`: `None` → `0.00` (present=True).
- gemma4:latest, 1099-G clean, `state_id`: `000QO1908` → `0000QO1908` (present=True).
- gemma4:latest, K-1 clean: shape mismatches ['', 'amt_items', 'distributions', 'foreign_transactions', 'other_credits', 'other_deductions', 'other_information', 'tax_exempt_and_nondeductible']; extra keys [].
- qwen3.5:4b, 1099-R clean, `payer_name`: `Juniper Example Works LLC` → `None` (present=False).
- qwen3.5:4b, 1099-R clean, `payer_tin`: `00-XXX0000` → `None` (present=False).
- qwen3.5:4b, 1099-R clean, `recipient_tin`: `XXX-XX-0000` → `None` (present=False).
- qwen3.5:4b, 1099-R clean, `recipient_name`: `Morgan Sample` → `None` (present=False).
- qwen3.5:4b, 1099-R clean, `account_number`: `SYN-0042` → `None` (present=False).
- qwen3.5:4b, 1099-R clean: shape mismatches ['']; extra keys [].
- glm-ocr:latest, 1099-R clean, `recipient_tin`: `XXX-XX-0000` → `None` (present=True).
- glm-ocr:latest, 1099-R clean, `ira_sep_simple`: `True` → `False` (present=True).
- glm-ocr:latest, 1099-R clean, `fatca_filing_requirement`: `None` → `False` (present=True).
- glm-ocr:latest, K-1 clean, `royalties`: `None` → `7` (present=True).
- glm-ocr:latest, K-1 clean, `other_income`: `None` → `None` (present=False).
- glm-ocr:latest, K-1 clean: shape mismatches []; extra keys ['amt_items', 'distributions', 'foreign_transactions', 'other_credits', 'other_deductions.13 Code W - Other deductions', 'other_income.11 Other income (loss)', 'other_information', 'tax_exempt_and_nondeductible'].

## Interpretation and limits

Highest observed local aggregate field match: `gemma3:12b`. Treat this as a tag-level follow-up candidate, not an immutable-checkpoint ranking or deployment recommendation.

Qwen produced three exact documents among its three successful extractions, but five empty/truncated-JSON failures reduce its aggregate to 70/224. That aggregate measures this run's reliability and strict contract outcome, not just OCR reading quality.

Local launch inventory has two digests for each requested tag (ggml/llamacpp representations); complete inventory and per-document resident metadata remain in the original metadata/raw files. Response identities were checked for both extraction and vision classification, but these observations cannot prove a unique immutable serving checkpoint.

Classification is separate: clean forms generally use text classification; image-only scans exercise vision classification. Extraction always receives the answer-key form type. Extraction seconds/page excludes separately recorded classification time; it includes rendering, network/model load, and CLI overhead where applicable. The timing denominator is the PDF page count, including on failed documents that may abort before all pages are attempted.

**Scope correction:** upstream `summary.json` files incorrectly label this a clean-form smoke benchmark. They are preserved verbatim. The actual scope is four changed types (1099-R, 1099-G, 1099-K, K-1), one synthetic grid case each, clean plus moderate image-only scans; eight PDFs / ten pages per model. `scope-and-aggregates.json` is the accurate additional scope/aggregation record.

The schemas contribute 30 R, 18 G, 26 K, and 38 K-1 graded leaves per variant (K-1 has 33 top-level properties, with coded objects expanded). K-1 spans two pages and includes coded-object merging, STMT, nulls, negative values, and separate charitable scalar/coded values. Checkboxes distinguish visibly false from not visible/null.

These are invented grid layouts, not representative real tax documents. One source case per form and paired variants cannot establish tax-preparation accuracy, robust OCR performance, or 1.0 approval. No production deployment, API/privacy sign-off, or live data use occurred in this evidence-packaging step.

## Reproduction

At source freeze `800b761` with the pinned dependencies, generate the omitted PDFs locally using `python -m benchmarks.taxclaw_accuracy.runner build --corpus changed-forms --output /tmp/taxclaw-changed-fixtures`. The manifest and PDFs must match the hashes in launch metadata and `verification.json`. For offline regrading, copy either archived run directory to a scratch directory and run `python -m benchmarks.taxclaw_accuracy.runner regrade --fixtures /tmp/taxclaw-changed-fixtures --output SCRATCH_RUN_DIR`; preserve the archived raw/receipt files. No model call is needed for rebuilding fixtures or regrading.

## Verification

Both runs were regraded with the frozen grader without changing raw results. Launch source hashes match `800b761`; manifest, eight PDF hashes, strict answer keys, every observed model identity, scoring receipts, and 48 individual raw-record hashes were checked. Fixture rebuilding reproduces manifest and PDFs byte-for-byte under recorded dependencies. See `verification.json`.

Parent reports 28 application and 14 benchmark tests passed. An initial unsuitable unittest discovery invocation was corrected to package invocation; it was not a code failure. Evidence worker performed deterministic provenance/regrading checks, not additional model calls.

## Later-main static compatibility note

Main subsequently advanced to `a47c572` (exports merged). Read-only comparison verified that all 12 pre-existing `src/extract.py` function ASTs are identical to measured main `87efee5`; the only added functions are `capital_lots_schema`, `extract_capital_lots`, and `page_may_have_lots`. `src/ai.py`, `src/backends.py`, `src/classify.py`, `src/config.py`, `src/ollama_local.py`, `src/clairic.py`, and `requirements.txt` blobs are identical. See `compatibility-note.json`. This supports an unchanged four-form extraction contract, but **the benchmark was not rerun on the newer head**. Its new per-lot/export path is outside WP-F scope and not verified here.

Original archived 84 baseline records and every file under the original `results/2026-10-20/` remain unchanged. They cover different source/schema conditions and are not pooled into this report.
