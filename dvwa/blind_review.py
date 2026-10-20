"""Export blinded candidate packets and import independently completed annotations."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from experiment_dataset import load_runs
from rag_pipeline import ROOT, load_catalog
from validation_loop import sanitized_review_excerpt_from_markers


def make_packets(runs):
    packets=[];mapping={}
    catalog={s['scenario_id']:s for s in load_catalog()['scenarios']}
    for run in runs:
        scenario=catalog[run['scenario_id']]
        for c in run['candidates']:
            review_id=uuid4().hex
            observations=[]
            for o in c['observations']:
                indicators=[v for v in o.get('response_indicators',[]) if v.startswith('mysql_')]
                markers=o.get('content_markers',[])
                excerpt=o.get('review_excerpt')
                excerpt_basis='captured_response_allowlist' if excerpt is not None else None
                if excerpt is None and ('response_indicators' in o and 'content_markers' in o):
                    excerpt=sanitized_review_excerpt_from_markers(indicators,markers)
                    excerpt_basis='recorded_allowlist_markers'
                observations.append({'trial':o['confirmation_index'],'role':o['payload_role'],
                                     'http_status':o['http_status'],'elapsed_ms':o['response_time_ms'],
                                     'response_sha256':o['response_sha256'],
                                     'review_excerpt':excerpt,
                                     'review_excerpt_basis':excerpt_basis,
                                     'diagnostics':indicators,
                                     'content_markers':markers})
            packets.append({'review_id':review_id,'technique':scenario['sqli_type'],
                            'injection_point':{k:scenario[k] for k in ('method','input_path','result_path','parameter')},
                            'candidate':c.get('payload', {k:c[k] for k in ('true_payload','false_payload') if k in c}),
                            'observations':observations})
            mapping[review_id]={k:run[k] for k in
                ('experiment_id','unit_id','attempt_id','run_id','scenario_id','condition_id','replicate')}
            mapping[review_id].update(candidate_id=c['candidate_id'])
    # Random order avoids leaking the A/B/C ledger order into the review package.
    packets.sort(key=lambda p:p['review_id'])
    return packets,mapping


def export(directory,output):
    return export_runs(load_runs(directory),output)


def export_runs(runs,output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'results/raw').resolve()):
        raise ValueError('Review output must stay under results/raw.')
    packets,mapping=make_packets(runs)
    output.mkdir(parents=True,exist_ok=False)
    public=output/'validator';public.mkdir()
    complete=all(o.get('review_excerpt') for p in packets for o in p['observations'])
    text=json.dumps({'scope':'blinded-candidate-review',
                     'review_readiness':'ready_for_pilot_review' if complete else 'incomplete_legacy_missing_excerpts',
                     'excerpt_policy':'normalized_allowlisted_phrases_from_capture_or_recorded_markers_v1',
                     'packets':packets},indent=2)+'\n'
    # Write the serialized UTF-8 bytes directly so Windows does not translate
    # LF into CRLF after the digest is calculated.
    package_bytes=text.encode('utf-8')
    (public/'packets.json').write_bytes(package_bytes)
    package_hash=hashlib.sha256(package_bytes).hexdigest()
    with (public/'annotations.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['review_id','validator_id','decision','justification'])
        w.writeheader()
        for p in packets:w.writerow({'review_id':p['review_id']})
    (output/'mapping.private.json').write_text(json.dumps({'package_sha256':package_hash,'mapping':mapping},indent=2)+'\n',encoding='utf-8')
    return {'review_candidates':len(packets),'validator_directory':str(public),'package_sha256':package_hash}


def import_annotations(package,annotations,validator_id):
    package=Path(package)
    if not isinstance(validator_id,str) or not validator_id.strip():raise ValueError('Validator identity is required.')
    private=json.loads((package/'mapping.private.json').read_text(encoding='utf-8'))
    # Existing Windows packages may have CRLF on disk even though their
    # manifest hashes the LF-serialized JSON. Normalize line endings before
    # checking integrity; JSON string contents are escaped and unaffected.
    raw=(package/'validator/packets.json').read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=private['package_sha256']:raise ValueError('Review package changed.')
    with Path(annotations).open(encoding='utf-8-sig',newline='') as source:
        rows=list(csv.DictReader(source))
    ids=[r['review_id'] for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)!=set(private['mapping']):
        raise ValueError('Annotations must cover every review ID exactly once.')
    result=[]
    for r in rows:
        if (r['validator_id']!=validator_id or r['decision'] not in {'success','failure','insufficient_evidence'}
                or not r['justification'].strip()):
            raise ValueError('Every decision requires validator identity, valid decision and justification.')
        result.append({**private['mapping'][r['review_id']],**r,'package_sha256':private['package_sha256']})
    return {'scope':'independent-human-annotations','validator_id':validator_id,'annotations':result}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    e=sub.add_parser('export');e.add_argument('--experiment-dir',type=Path,required=True);e.add_argument('--output-dir',type=Path,required=True)
    i=sub.add_parser('import');i.add_argument('--package-dir',type=Path,required=True);i.add_argument('--annotations',type=Path,required=True);i.add_argument('--validator-id',required=True);i.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='export':print(json.dumps(export(a.experiment_dir,a.output_dir)))
    else:
        result=import_annotations(a.package_dir,a.annotations,a.validator_id)
        if not a.output.resolve().is_relative_to((ROOT/'results/raw').resolve()):raise ValueError('Output must stay under results/raw.')
        with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
        print(json.dumps({'output':str(a.output),'annotations':len(result['annotations'])}))


if __name__=='__main__':main()
