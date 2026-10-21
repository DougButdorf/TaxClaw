"""Summarize the supported-13 gate without altering strict scoring."""
from pathlib import Path
import json
from benchmarks.taxclaw_accuracy.runner import write_json,digest
root=Path(__file__).parent
run=root/'haiku-subscription'
rows=[json.loads(s) for s in (run/'scored-results.jsonl').read_text().splitlines()]
assert len(rows)==26
report={'application_revision':json.loads((root/'freeze.json').read_text())['application_revision'],'scope':'13 supported information-form types, clean and degraded; best-effort 1040 not rerun','transport':'Haiku subscription CLI image adapter, not production API verification','strict_scorer_sha256':digest(Path('benchmarks/taxclaw_accuracy/grader.py')),'variants':{}}
for variant in ['clean','degraded_scan','both']:
 subset=rows if variant=='both' else [r for r in rows if r['variant']==variant]
 report['variants'][variant]={'documents':len(subset),'pages':sum(r['page_count'] for r in subset),'correct_fields':sum(r['score']['correct'] for r in subset),'expected_fields':sum(r['score']['expected_fields'] for r in subset),'exact_documents':sum(r['score']['exact_document'] for r in subset),'classifications_correct':sum(r['classification_correct'] for r in subset),'runtime_errors':sum(r['status']!='ok' for r in subset),'dedicated_schemas':sum(r['dedicated_prompt'] for r in subset),'extraction_seconds_per_page':sum(r['extraction_seconds'] for r in subset)/sum(r['page_count'] for r in subset),'release_gate_passed':all(r['dedicated_prompt'] and r['classification_correct'] and r['status']=='ok' and r['score']['exact_document'] for r in subset),'failed_documents':[{'fixture_id':r['fixture_id'],'score':r['score'],'error':r.get('error')} for r in subset if not r['score']['exact_document'] or not r['classification_correct'] or r['status']!='ok']}
write_json(root/'gate-report.json',report)
print(json.dumps(report,indent=2))
