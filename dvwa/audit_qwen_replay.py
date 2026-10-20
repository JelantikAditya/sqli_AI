"""Replay a predeclared diagnostic fixture set without sending DVWA probes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from analyze_response import (ROOT, analyze_with_qwen, normalize_analysis, sha256,
                              validate_input, PROMPT_VERSION)


def fixtures(source):
    reference = next(r for r in source['candidate_records'] if r['confirmed_success'])
    base = reference['evidence']
    cases = []
    for name, count, expected in [('diagnostic-3', 3, 'positive'), ('diagnostic-0', 0, 'negative'),
                                  ('mixed-1', 1, 'inconclusive'), ('mixed-2', 2, 'inconclusive'),
                                  ('generic-500', 0, 'negative'), ('incomplete-2-trials', 2, 'inconclusive'),
                                  ('invalid-session', 0, None)]:
        doc = copy.deepcopy(base)
        for o in doc['observations']:
            if o['role'] == 'candidate':
                o['diagnostics'] = ['mysql_syntax_error'] if o['trial'] <= count else []
                if name == 'generic-500': o['http_status'] = 500
        if name == 'incomplete-2-trials':
            doc['observations'] = [o for o in doc['observations'] if o['trial'] <= 2]
        if name == 'invalid-session':
            doc['runtime_status'], doc['baseline_valid'] = 'invalid', False
        ctx = {**reference['context'], 'experiment_id': 'u01-replay-20261014',
               'run_id': name, 'attempt_id': 'replay-1', 'candidate_id': 'candidate-001'}
        validate_input(doc)
        cases.append({'case_id': name, 'input': doc, 'context': ctx, 'expected_claim': expected})
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--call-model', action='store_true')
    p.add_argument('--stored-replay', type=Path,
                   help='Re-normalize saved model outputs by case_id without calling Qwen.')
    a=p.parse_args()
    out=a.output_dir.resolve()
    if not out.is_relative_to((ROOT/'results/raw').resolve()):
        raise ValueError('Replay output must stay under results/raw.')
    out.mkdir(parents=True, exist_ok=False)
    source=json.loads(a.source.read_text(encoding='utf-8'))
    cases=fixtures(source)
    (out/'fixtures.json').write_text(json.dumps(cases,indent=2)+'\n',encoding='utf-8')
    stored = None
    if a.stored_replay:
        stored = {}
        for line in a.stored_replay.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['case_id'] in stored:
                raise ValueError(f"Duplicate stored case_id: {row['case_id']}")
            stored[row['case_id']] = row['record']
        expected_ids = {case['case_id'] for case in cases}
        if set(stored) != expected_ids:
            raise ValueError('Stored replay case IDs do not match the fixed fixture set.')
    integrity=[]
    for r in source['candidate_records']:
        integrity.append(r==normalize_analysis(r['evidence'],r['model_output'],r['context'],r['audit']['provenance']))
    results=[]
    if a.call_model:
        with (out/'replay.jsonl').open('x',encoding='utf-8') as f:
            for case in cases:
                r=analyze_with_qwen(case['input'],case['context'])
                row={'case_id':case['case_id'], 'expected_claim':case['expected_claim'],
                     'matches_expected':r['system_claim']==case['expected_claim'], 'record':r}
                f.write(json.dumps(row)+'\n'); f.flush(); results.append(row)
                print(json.dumps({k:row[k] for k in ('case_id','expected_claim','matches_expected')}),flush=True)
    elif stored is not None:
        with (out/'replay.jsonl').open('x',encoding='utf-8') as f:
            for case in cases:
                prior = stored[case['case_id']]
                record = normalize_analysis(case['input'], prior['model_output'], case['context'],
                                            copy.deepcopy(prior['audit']['provenance']))
                row={'case_id':case['case_id'], 'expected_claim':case['expected_claim'],
                     'matches_expected':record['system_claim']==case['expected_claim'], 'record':record}
                f.write(json.dumps(row)+'\n'); f.flush(); results.append(row)
                print(json.dumps({k:row[k] for k in ('case_id','expected_claim','matches_expected')}),flush=True)
    summary={'scope':'development-replay-not-formal','source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),
             'source_record_count':len(integrity), 'source_normalization_unchanged':all(integrity),
             'prompt_version':PROMPT_VERSION, 'fixtures_sha256':sha256(cases),
             'model_called':a.call_model, 'stored_model_outputs_replayed':stored is not None,
             'stored_replay_sha256':hashlib.sha256(a.stored_replay.read_bytes()).hexdigest() if a.stored_replay else None,
             'dvwa_requests_sent':0,
             'results':[{'case_id':r['case_id'],'expected_claim':r['expected_claim'],
                         'actual_claim':r['record']['system_claim'], 'matches_expected':r['matches_expected'],
                         'analysis_status':r['record']['analysis_status']} for r in results]}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(out/'summary.json')}),flush=True)


if __name__=='__main__': main()
