"""Aggregate validated pilot/formal annotations and system run claims."""
import argparse
import csv
import json
import statistics
from pathlib import Path
from experiment_dataset import load_runs
from rag_pipeline import ROOT, load_catalog


def mean_sd(values):
    if len(values)!=3 or any(v is None for v in values):return {'mean':None,'sample_sd':None,'n':sum(v is not None for v in values)}
    return {'mean':statistics.mean(values),'sample_sd':statistics.stdev(values),'n':3}


def aggregate(runs,annotations,*,experiment_id=None):
    runs=list(runs)
    annotations=list(annotations)
    catalog={s['scenario_id']:s['ground_truth'] for s in load_catalog()['scenarios']}
    positive_scenarios={s for s,truth in catalog.items() if truth=='positive'}
    negative_scenarios={s for s,truth in catalog.items() if truth=='negative'}
    if positive_scenarios!={f'S{i}' for i in range(1,10)} or negative_scenarios!={f'S{i}' for i in range(10,13)}:
        raise ValueError('Scenario catalog ground truth does not match the locked U05 metric scope.')
    keys=[(x['unit_id'],x['candidate_id']) for x in annotations]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate validator annotation.')
    run_keys=[(r['experiment_id'],r['condition_id'],r['scenario_id'],r['replicate']) for r in runs]
    if len(run_keys)!=len(set(run_keys)):raise ValueError('Duplicate condition-run in dataset.')
    candidate_keys={(r['unit_id'],c['candidate_id']) for r in runs for c in r.get('candidates',[])}
    if set(keys)-candidate_keys:raise ValueError('Validator annotation refers to an unknown candidate.')
    amap={(x['unit_id'],x['candidate_id']):x for x in annotations}
    if experiment_id and any(r['experiment_id']!=experiment_id for r in runs):raise ValueError('Dataset mixes experiment IDs.')
    result={'scope':'validated-experiment-metrics-no-formality-asserted',
            'experiment_ids':sorted({r['experiment_id'] for r in runs}),
            'annotations_complete':False,'psr':{'eligible':False,'condition_replicates':[],'per_scenario':[]},
            'fpr':{'eligible':False,'condition_replicates':[]},'system_confusion':{'condition_replicates':[]}}
    psr_runs=[]
    for run in runs:
        if run['condition_id'] not in {'B','C'} or run['scenario_id'] not in positive_scenarios:continue
        if not run['metric_eligible'] or run['status']!='completed':
            reason=('run_status_'+run['status']) if run['status']!='completed' else 'metric_ineligible'
            psr_runs.append({'unit_id':run['unit_id'],'condition_id':run['condition_id'],'scenario_id':run['scenario_id'],
                'replicate':run['replicate'],'eligible':False,'reason':reason,
                'valid_candidates':len(run.get('candidates',[]))})
            continue
        decisions=[]
        for c in run['candidates']:
            a=amap.get((run['unit_id'],c['candidate_id']))
            if a is None or a['decision'] not in {'success','failure','insufficient_evidence'}:break
            decisions.append(a)
        if len(decisions)!=len(run['candidates']) or not decisions:
            psr_runs.append({'unit_id':run['unit_id'],'condition_id':run['condition_id'],'scenario_id':run['scenario_id'],
                'replicate':run['replicate'],'eligible':False,'reason':'missing_or_incomplete_annotation',
                'valid_candidates':len(run['candidates'])})
            continue
        success=sum(a['decision']=='success' and c['confirmed_success'] is True
                    and c['evidence_status']=='CONSISTENT_POSITIVE'
                    for a,c in zip(decisions,run['candidates']))
        psr_runs.append({'unit_id':run['unit_id'],'condition_id':run['condition_id'],'scenario_id':run['scenario_id'],
            'replicate':run['replicate'],'eligible':True,'success_count':success,
            'valid_candidates':len(run['candidates']),'psr':success/len(run['candidates'])})
    result['psr']['per_run']=psr_runs
    scenario_rows=[]
    for condition in ('B','C'):
        for scenario in [f'S{i}' for i in range(1,10)]:
            rows=[x for x in psr_runs if x['condition_id']==condition and x['scenario_id']==scenario]
            by_rep={x['replicate']:x for x in rows}
            complete=all(r in by_rep and by_rep[r]['eligible'] for r in (1,2,3))
            stats=mean_sd([by_rep[r]['psr'] if complete else None for r in (1,2,3)])
            scenario_rows.append({'condition_id':condition,'scenario_id':scenario,**stats,'eligible':complete})
    result['psr']['per_scenario']=scenario_rows
    replicate_rows=[]
    for condition in ('B','C'):
        for rep in (1,2,3):
            rows=[x for x in psr_runs if x['condition_id']==condition and x['replicate']==rep and x['eligible']]
            expected=positive_scenarios
            seen={x['scenario_id'] for x in rows}
            n=sum(x['valid_candidates'] for x in rows);s=sum(x['success_count'] for x in rows)
            replicate_rows.append({'condition_id':condition,'replicate':rep,'eligible':seen==expected and n>0,
                'scenario_count':len(seen),'success_count':s,'valid_candidates':n,
                'psr':s/n if seen==expected and n else None,'missing_scenarios':sorted(expected-seen)})
    result['psr']['condition_replicates']=replicate_rows
    by_condition=[]
    for condition in ('B','C'):
        rows=[x for x in replicate_rows if x['condition_id']==condition]
        complete=all(x['eligible'] for x in rows)
        stats=mean_sd([x['psr'] if x['eligible'] else None for x in rows])
        by_condition.append({'condition_id':condition,**stats,'eligible':complete})
    result['psr']['summary']=by_condition
    result['psr']['eligible']=all(x['eligible'] for x in by_condition)

    fpr_rows=[]
    for condition in ('A','B'):
        for rep in (1,2,3):
            rows=[r for r in runs if r['condition_id']==condition and r['replicate']==rep
                  and r['scenario_id'] in negative_scenarios]
            by_scenario={r['scenario_id']:r for r in rows}
            fp=tn=0;unresolved=[]
            for sid in sorted(negative_scenarios):
                r=by_scenario.get(sid);summary=r.get('analysis_summary') if r else None
                if (not r or r['status']!='completed' or not r['metric_eligible'] or not summary
                        or not summary.get('binary_decision_eligible')):
                    unresolved.append(sid);continue
                decision=summary['system_decision']
                if decision=='positive':fp+=1
                elif decision=='negative':tn+=1
                else:unresolved.append(sid)
            eligible=not unresolved and len(by_scenario)==3
            total=fp+tn
            fpr_rows.append({'condition_id':condition,'replicate':rep,'FP':fp,'TN':tn,
                'unresolved_scenarios':sorted(set(unresolved)),'decision_coverage':total/3,
                'eligible':eligible,'reason':None if eligible else 'planned_negative_missing_invalid_or_abstained',
                'fpr':fp/total if eligible and total else None})
    result['fpr']['condition_replicates']=fpr_rows
    fpr_summary=[]
    for condition in ('A','B'):
        rows=[x for x in fpr_rows if x['condition_id']==condition]
        complete=all(x['eligible'] for x in rows)
        stats=mean_sd([x['fpr'] if x['eligible'] else None for x in rows])
        fpr_summary.append({'condition_id':condition,**stats,'eligible':complete})
    result['fpr']['summary']=fpr_summary
    result['fpr']['eligible']=all(x['eligible'] for x in fpr_summary)
    confusion_rows=[]
    for condition in ('A','B'):
        for rep in (1,2,3):
            rows=[r for r in runs if r['condition_id']==condition and r['replicate']==rep]
            by_scenario={r['scenario_id']:r for r in rows}
            counts={'TP':0,'FP':0,'TN':0,'FN':0};unresolved=[]
            for sid,truth in catalog.items():
                r=by_scenario.get(sid);summary=r.get('analysis_summary') if r else None
                if (not r or r['status']!='completed' or not r['metric_eligible'] or not summary
                        or not summary.get('binary_decision_eligible')):
                    unresolved.append(sid);continue
                decision=summary.get('system_decision')
                if decision not in {'positive','negative'}:
                    unresolved.append(sid);continue
                label={('positive','positive'):'TP',('positive','negative'):'FN',
                       ('negative','positive'):'FP',('negative','negative'):'TN'}[(truth,decision)]
                counts[label]+=1
            confusion_rows.append({'condition_id':condition,'replicate':rep,**counts,
                'decision_coverage':sum(counts.values())/len(catalog),
                'unresolved_scenarios':sorted(set(unresolved)),
                'eligible':not unresolved and len(by_scenario)==len(catalog),
                'reason':None if not unresolved and len(by_scenario)==len(catalog) else 'planned_scenario_missing_invalid_or_abstained'})
    result['system_confusion']['condition_replicates']=confusion_rows
    result['annotations_complete']=all(x['eligible'] for x in scenario_rows)
    result['ground_truth']={'positive_scenarios':sorted(positive_scenarios),
                            'negative_scenarios':sorted(negative_scenarios),
                            'source':'dvwa/experiment_scenarios.json'}
    return result


def csv_rows(report):
    """Flatten metric outputs while keeping each reported value traceable to its unit."""
    columns=('row_type','metric','condition_id','scenario_id','replicate','unit_id','eligible',
             'numerator','denominator','TP','FP','TN','FN','value','mean','sample_sd','n','coverage','reason','unresolved_scenarios','missing_scenarios')
    rows=[]
    def add(row_type,metric,source,**extra):
        row={'row_type':row_type,'metric':metric,**extra}
        for key in ('condition_id','scenario_id','replicate','unit_id','eligible','reason','missing_scenarios','unresolved_scenarios','TP','FP','TN','FN'):
            if key in source: row[key]=source[key]
        if isinstance(row.get('missing_scenarios'),list):row['missing_scenarios']=';'.join(row['missing_scenarios'])
        if isinstance(row.get('unresolved_scenarios'),list):row['unresolved_scenarios']=';'.join(row['unresolved_scenarios'])
        rows.append({key:row.get(key) for key in columns})
    for source in report['psr'].get('per_run',[]):
        add('run','PSR',source,numerator=source.get('success_count'),denominator=source.get('valid_candidates'),value=source.get('psr'))
    for source in report['psr'].get('per_scenario',[]):
        add('scenario','PSR',source,mean=source.get('mean'),sample_sd=source.get('sample_sd'),n=source.get('n'))
    for source in report['psr'].get('condition_replicates',[]):
        add('replicate','PSR',source,numerator=source.get('success_count'),denominator=source.get('valid_candidates'),value=source.get('psr'),coverage=source.get('scenario_count'),reason='missing_positive_scenarios' if source.get('missing_scenarios') else None)
    for source in report['psr'].get('summary',[]):
        add('summary','PSR',source,mean=source.get('mean'),sample_sd=source.get('sample_sd'),n=source.get('n'))
    for source in report['fpr'].get('condition_replicates',[]):
        add('replicate','FPR',source,numerator=source.get('FP'),denominator=(source.get('FP',0)+source.get('TN',0)),value=source.get('fpr'),coverage=source.get('decision_coverage'),reason=source.get('reason'),unresolved_scenarios=';'.join(source.get('unresolved_scenarios',[])))
    for source in report['fpr'].get('summary',[]):
        add('summary','FPR',source,mean=source.get('mean'),sample_sd=source.get('sample_sd'),n=source.get('n'))
    for source in report.get('system_confusion',{}).get('condition_replicates',[]):
        add('replicate','system_confusion',source,numerator=None,denominator=12,coverage=source.get('decision_coverage'),reason=source.get('reason'))
    return columns,rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment-dir',type=Path,required=True)
    p.add_argument('--annotations',type=Path,required=True,help='Imported independent annotation JSON')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--csv-output',type=Path,required=True,help='Traceable tabular export under results/raw')
    a=p.parse_args();out=a.output.resolve();csv_out=a.csv_output.resolve()
    raw_root=(ROOT/'results/raw').resolve()
    if not out.is_relative_to(raw_root) or not csv_out.is_relative_to(raw_root):raise ValueError('Outputs must stay under results/raw.')
    if out==csv_out:raise ValueError('JSON and CSV outputs must use different paths.')
    imported=json.loads(a.annotations.read_text(encoding='utf-8'))
    if imported.get('scope')!='independent-human-annotations' or not imported.get('validator_id'):
        raise ValueError('Expected an identified independent validator annotation file.')
    runs=load_runs(a.experiment_dir)
    report=aggregate(runs,imported['annotations'])
    report['validator_id']=imported['validator_id'];report['source_ledger_sha256']=__import__('hashlib').sha256((a.experiment_dir/'ledger.jsonl').read_bytes()).hexdigest()
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    csv_out.parent.mkdir(parents=True,exist_ok=True)
    columns,rows=csv_rows(report)
    with csv_out.open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(rows)
    print(json.dumps({'output':str(out),'csv_output':str(csv_out),'psr_eligible':report['psr']['eligible'],'fpr_eligible':report['fpr']['eligible']}))


if __name__=='__main__':main()
