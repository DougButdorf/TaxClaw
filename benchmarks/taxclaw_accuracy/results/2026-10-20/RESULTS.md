# WP-F synthetic contract evaluation — 2026-10-20

**No evaluated model passes the strict 12-form smoke gate.** These are strict canonical-contract measurements on synthetic clean forms, not OCR accuracy, tax-preparation accuracy, real-world accuracy, or release qualification.

## Scope and provenance

- 12 documents / 14 pages / 233 expected canonical leaf fields, one invented example per type. Eleven types classify from PDF text; K-1 uses vision fallback. All models classify 12/12 correctly except GLM-OCR (11/12: K-1 JSON parse failure). Extraction uses the known type, so this is not end-to-end ingest or scan-only classification.
- `app-baseline` (five local models) and `haiku-subscription` (first Haiku pass) are **exploratory pre-freeze inference**. Launch-time runner/grader hashes and digest-bound resume signatures were absent. Original application source, fixture, package, inventory and raw-response evidence remains intact; `launch-caveat.json` states the limitation.
- `haiku-frozen` launched at commit `f08e48d` with benchmark/application source hashes, wrapper hash and fixture hashes captured. Both Haiku passes are reported; the lower frozen result is not discarded.
- All three runs were regraded using the current strict scorer without changing raw inference. `scoring.json` binds raw records, manifest and grader hashes. `verification.json` verifies counts, source/PDF hashes, every recorded provider model identity, and byte-identical evidence copies. Seven grader tests passed.
- **Local checkpoint ambiguity:** response tags match requests, but resident digests change within Qwen (`2a654d98…` to `96f38c74…`, sometimes both listed) and Gemma 4 (`c6eb396d…` on W-2, `9ec987e7…` afterward). Launch inventory also has duplicate/mismatching digests. Resident snapshots are not per-call attestations. Local aggregates are requested-tag observations, **not verified single-immutable-checkpoint results**; all full digest sets are retained in `verification.json`.
- PDFs are not duplicated here. [The deterministic generator](../../fixtures.py) plus `manifest.json` reproduces them; the receipt checks the original PDF hashes.

## Aggregate strict canonical results

Field-match rates use expected canonical fields as the denominator. Extra fields do not reduce that rate but prevent an exact-document pass. Populated-only rates exclude expected nulls. Unsupported schemas remain in the full-corpus denominator.

| Run | Model | Strict fields | Populated | Exact docs | Errors | Classified | Seconds/page |
|---|---|---:|---:|---:|---:|---:|---:|
| app-baseline | gemma3:12b | 177/233 (75.97%) | 75.37% | 3/12 | 0 | 12/12 | 36.89 |
| app-baseline | gemma3:4b | 155/233 (66.52%) | 69.46% | 2/12 | 0 | 12/12 | 15.42 |
| app-baseline | qwen3.5:4b | 130/233 (55.79%) | 55.17% | 7/12 | 1 | 12/12 | 49.90 |
| app-baseline | glm-ocr:latest | 0/233 (0.00%) | 0.00% | 0/12 | 12 | 11/12 | 24.71 |
| app-baseline | gemma4:latest | 183/233 (78.54%) | 78.33% | 7/12 | 0 | 12/12 | 52.01 |
| haiku-frozen | claude-haiku-5-5 | 190/233 (81.55%) | 79.80% | 6/12 | 0 | 12/12 | 4.27 |
| haiku-subscription | claude-haiku-5-5 | 193/233 (82.83%) | 81.28% | 9/12 | 0 | 12/12 | 4.44 |

Seconds/page is total extraction wall time / total PDF pages, including rendering, network and model load; it excludes classification. Haiku additionally includes subscription CLI startup/infrastructure, not application SDK/API latency or cost. No statistical speed or quality claim follows from one sweep.

## Per-form strict fields and observed seconds/page

Each cell is **correct/expected @ seconds/page**. All 12 types are shown; these are canonical matches, not a count of correctly read text tokens.

| Form | gemma3:12b | gemma3:4b | qwen3.5:4b | glm-ocr:latest | gemma4:latest |
|---|---:|---:|---:|---:|---:|
| W-2 | 8/10 @ 35.16 | 8/10 @ 19.43 | 8/10 @ 53.74 | 0/10 @ 28.93 | 8/10 @ 125.31 |
| 1099-NEC | 6/6 @ 14.02 | 5/6 @ 18.04 | 6/6 @ 26.85 | 0/6 @ 29.76 | 6/6 @ 28.47 |
| 1099-INT | 8/8 @ 36.54 | 8/8 @ 7.40 | 8/8 @ 27.48 | 0/8 @ 29.32 | 8/8 @ 24.38 |
| 1099-DIV | 19/21 @ 33.51 | 19/21 @ 13.39 | 21/21 @ 59.36 | 0/21 @ 27.85 | 21/21 @ 51.46 |
| consolidated-1099 | 15/20 @ 32.61 | 13/20 @ 13.50 | 20/20 @ 47.73 | 0/20 @ 29.46 | 20/20 @ 64.43 |
| 1099-B | 12/14 @ 24.16 | 10/14 @ 9.62 | 14/14 @ 35.64 | 0/14 @ 30.11 | 14/14 @ 32.55 |
| 1099-MISC | 16/17 @ 26.98 | 14/17 @ 10.63 | 17/17 @ 40.76 | 0/17 @ 29.46 | 17/17 @ 36.65 |
| 1099-OID | 12/12 @ 21.45 | 12/12 @ 8.93 | 12/12 @ 63.51 | 0/12 @ 28.96 | 12/12 @ 30.18 |
| K-1 | 23/29 @ 44.66 | 21/29 @ 15.20 | 24/29 @ 73.86 | 0/29 @ 8.71 | 23/29 @ 66.18 |
| 1099-DA | 58/61 @ 68.80 | 45/61 @ 29.75 | 0/61 @ 41.28 | 0/61 @ 16.67 | 54/61 @ 69.22 |
| 1099-R | 0/16 @ 27.92 | 0/16 @ 11.03 | 0/16 @ 67.64 | 0/16 @ 30.97 | 0/16 @ 29.09 |
| 1040 | 0/19 @ 37.24 | 0/19 @ 13.94 | 0/19 @ 45.56 | 0/19 @ 30.33 | 0/19 @ 34.82 |

| Form | Haiku frozen | Haiku initial exploratory |
|---|---:|---:|
| W-2 | 10/10 @ 3.23 | 10/10 @ 6.80 |
| 1099-NEC | 6/6 @ 2.74 | 6/6 @ 2.67 |
| 1099-INT | 8/8 @ 4.17 | 8/8 @ 3.50 |
| 1099-DIV | 21/21 @ 4.92 | 21/21 @ 4.84 |
| consolidated-1099 | 20/20 @ 4.31 | 20/20 @ 3.34 |
| 1099-B | 13/14 @ 2.66 | 14/14 @ 3.93 |
| 1099-MISC | 16/17 @ 4.76 | 17/17 @ 4.50 |
| 1099-OID | 11/12 @ 3.60 | 12/12 @ 4.01 |
| K-1 | 24/29 @ 5.78 | 24/29 @ 4.58 |
| 1099-DA | 61/61 @ 4.62 | 61/61 @ 4.40 |
| 1099-R | 0/16 @ 5.34 | 0/16 @ 5.26 |
| 1040 | 0/19 @ 3.31 | 0/19 @ 5.30 |

## What the misses mean

- **Unsupported canonical schemas:** 1099-R and 1040 use the generic prompt. They may contain correctly read values under human-label keys while earning zero canonical fields. That is a support/contract gap, not proof of OCR failure.
- **Correct value, noncanonical serialization:** frozen Haiku returned tax year `2025` as an integer on 1099-B, 1099-MISC and 1099-OID, versus canonical string `"2025"`; the first pass returned strings. The compact application prompts do not specify tax-year type. These three strict misses explain the Haiku aggregate difference, not changed financial readings.
- Both Haiku passes have all five K-1 coded values present (`87.65`, `0.00`, `Canada`, `-32.10`, `127.90`) under noncanonical keys: initial `13W`/`15A`/`16A_country`/`17A`/`20A`, frozen verbose box-label keys, versus canonical `W`/`A`. No semantic credit was added. Other verified year/code-key cases, including W-2, are itemized in `serialization-cases.json`.
- **Actual field/value errors also occur:** for example, Gemma 3 12B assigns the DIV foreign-tax value `23.45` to investment expenses, shifts some consolidated-statement amounts to adjacent fields, and drops masking/leading identifier characters. These are distinct from code-key/year serialization mismatches. Per-field evidence remains in each scored result.
- **Response failures:** Qwen 3.5 4B failed 1099-DA with empty content and provider `done_reason=length`, causing JSONDecodeError. GLM-OCR failed the application JSON contract across its attempted forms; the W-2 response repeats fenced JSON objects and ends at the length limit. Failed documents receive zero credit; raw responses are retained, not repaired or silently omitted.

Original runtime error counts and messages:

- `app-baseline` / `qwen3.5:4b`: 1 document(s), `JSONDecodeError: Expecting value`.
- `app-baseline` / `glm-ocr:latest`: 11 document(s), `JSONDecodeError: Extra data`.
- `app-baseline` / `glm-ocr:latest`: 1 document(s), `JSONDecodeError: Expecting ':' delimiter`.
- `haiku-frozen`: no runtime errors.
- `haiku-subscription`: no runtime errors.

## Recommendation

No deployment or release-accuracy recommendation. Keep frozen Haiku as a bounded reference comparator; `gemma4:latest` is only a local requested-tag follow-up candidate by this strict full-corpus measure, **not a verified checkpoint recommendation**. Resolve dedicated 1099-R/1040 schemas and explicit year/code-key contracts before interpreting their misses as model reading quality. Do not promote any model from this single synthetic example per type. Clairic was not integrated or measured. Machine-readable decision: `recommendation.json`.
