"""Read final ledger attempts with checked artifact hashes, without changing logs."""
import hashlib
import json
from pathlib import Path
from analyze_response import sha256, summarize_run
from run_local_experiments import ExperimentLedger


def read_checked(directory, value, expected):
    p=Path(value).resolve()
    if not p.is_relative_to(directory.resolve()) or not p.is_file():
        raise ValueError('Artifact must exist inside its experiment directory.')
    if not expected or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
        raise ValueError('Artifact hash mismatch: '+p.name)
    return p


def load_runs(directory):
    directory=Path(directory).resolve()
    events=[json.loads(line) for line in (directory/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
    if not events or [e['sequence'] for e in events]!=list(range(1,len(events)+1)):
        raise ValueError('Ledger event sequence is not contiguous.')
    experiment=events[0]['experiment_id']
    if any(e['experiment_id']!=experiment for e in events):
        raise ValueError('Ledger mixes experiments.')
    states=ExperimentLedger(directory,experiment,events).statuses()
    runs=[]
    for unit_id,state in states.items():
        unit=state['unit']
        final=next((e for e in reversed(events) if e.get('unit_id')==unit_id
                    and e['event_type']=='attempt_completed'
                    and e.get('attempt_id')==state.get('last_attempt_id')),None)
        run={'unit_id':unit_id,'experiment_id':experiment,'scenario_id':unit['scenario_id'],
             'condition_id':unit['condition_id'],'replicate':unit['replicate'],
             'status':state['status'],'metric_eligible':False,'candidates':[],
             'analysis_summary':None,'attempt_id':state.get('last_attempt_id')}
        if final and state['status'] in {'completed','excluded'}:
            run.update(metric_eligible=final['metric_eligible'],candidate_budget=final['candidate_budget'],
                       run_id=final['run_id'])
            if final['valid_candidates_executed']:
                batch=json.loads(read_checked(directory,final['runner_batch_path'],final['runner_batch_sha256']).read_text(encoding='utf-8'))
                path=read_checked(directory,final['validation_log_path'],final['validation_log_sha256'])
                logs=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
                evidence={r['candidate_id']:r for r in logs if r['record_type']=='candidate_evidence'}
                if len(evidence)!=len(batch['candidates']): raise ValueError('Candidate evidence count mismatch.')
                for candidate in batch['candidates']:
                    cid=candidate['candidate_id'];ev=evidence[cid]
                    if any(ev.get(k)!=final[k] for k in ('run_id','attempt_id','condition_id','scenario_id','replicate')):
                        raise ValueError('Candidate evidence context mismatch.')
                    observations=[r for r in logs if r['record_type']=='payload' and r['candidate_id']==cid]
                    run['candidates'].append({'candidate_id':cid,'confirmed_success':ev['confirmed_success'],
                                              'evidence_status':ev['evidence_status'],
                                              'payload':{k:candidate[k] for k in ('payload','true_payload','false_payload') if k in candidate},
                                              'observations':observations})
                if final.get('adaptive_result_path'):
                    adaptive=json.loads(read_checked(directory,final['adaptive_result_path'],final['adaptive_result_sha256']).read_text(encoding='utf-8'))
                    if sha256(adaptive['events'])!=adaptive['events_sha256']:
                        raise ValueError('Adaptive event hash mismatch.')
                    summary=summarize_run(adaptive['candidate_records'],final['candidate_budget'])
                    if summary!=adaptive['run_summary']:
                        raise ValueError('Adaptive summary mismatch.')
                    if summary['context']['run_id']!=final['run_id'] or summary['context']['attempt_id']!=final['attempt_id']:
                        raise ValueError('Analysis belongs to a different attempt.')
                    run['analysis_summary']=summary
        runs.append(run)
    return runs
