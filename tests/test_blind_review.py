import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dvwa'))
from blind_review import export, import_annotations


class BlindReviewTests(unittest.TestCase):
    def test_export_keeps_random_public_ids_separate_from_condition_mapping(self):
        runs=[{'unit_id':'private-unit','experiment_id':'private-experiment','attempt_id':'private-attempt',
               'run_id':'private-run','condition_id':'B','scenario_id':'S1','replicate':1,
               'candidates':[{'candidate_id':'private-candidate','payload':{'payload':"1'"},
                   'observations':[{'confirmation_index':1,'payload_role':'single','http_status':200,
                       'response_time_ms':9,'response_sha256':'a'*64,'response_indicators':['mysql_syntax_error'],
                       'review_excerpt':'You have an error in your SQL syntax [query details redacted]',
                       'content_markers':[]}]}]}]
        with patch('blind_review.load_runs',return_value=runs):
            packets,mapping=__import__('blind_review').make_packets(runs)
        public=json.dumps(packets[0])
        for secret in ('private-unit','private-experiment','private-attempt','private-run','private-candidate','condition_id','ground_truth'):
            self.assertNotIn(secret,public)
        self.assertEqual(mapping[packets[0]['review_id']]['condition_id'],'B')
        self.assertNotIn('response_body',public)
        self.assertIn('query details redacted',public)

    def test_export_keeps_three_mixed_trials_without_executor_verdict_or_condition(self):
        observations=[]
        for trial in range(1,4):
            observations.extend([
                {'confirmation_index':trial,'payload_role':'baseline','http_status':200,
                 'response_time_ms':10,'response_sha256':str(trial)*64,'response_indicators':[],
                 'content_markers':['benign_record'],'review_excerpt':'First name: [record value redacted]'},
                {'confirmation_index':trial,'payload_role':'single','http_status':200,
                 'response_time_ms':11,'response_sha256':str(trial+3)*64,
                 'response_indicators':['mysql_syntax_error'] if trial < 3 else [],
                 'content_markers':[],'review_excerpt':'You have an error in your SQL syntax [query details redacted]' if trial < 3 else '[No allowlisted response phrase detected]'},
            ])
        runs=[{'unit_id':'u','experiment_id':'e','attempt_id':'a','run_id':'r','condition_id':'B',
               'scenario_id':'S1','replicate':1,'candidates':[{'candidate_id':'c','payload':{'payload':"1'"},
               'confirmed_success':False,'evidence_status':'MIXED','observations':observations}]}]
        with patch('blind_review.load_runs',return_value=runs):
            packets,mapping=__import__('blind_review').make_packets(runs)
        public=json.dumps(packets[0])
        self.assertEqual(len(packets[0]['observations']),6)
        self.assertEqual([o['trial'] for o in packets[0]['observations'] if o['role']=='single'],[1,2,3])
        for secret in ('condition_id','ground_truth','confirmed_success','evidence_status','MIXED'):
            self.assertNotIn(secret,public)
        self.assertEqual(mapping[packets[0]['review_id']]['condition_id'],'B')

    def test_legacy_export_is_not_marked_ready_for_review(self):
        runs=[{'unit_id':'u','experiment_id':'e','attempt_id':'a','run_id':'r','condition_id':'A',
               'scenario_id':'S1','replicate':1,'candidates':[{'candidate_id':'c','payload':{'payload':"1'"},
               'observations':[{'confirmation_index':1,'payload_role':'single','http_status':200,
                   'response_time_ms':9,'response_sha256':'a'*64}]}]}]
        with patch('blind_review.load_runs',return_value=runs), tempfile.TemporaryDirectory(dir=ROOT/'results/raw') as temp:
            result=export(ROOT/'unused',Path(temp)/'package')
            package=json.loads((Path(result['validator_directory'])/'packets.json').read_text())
        self.assertEqual(package['review_readiness'],'incomplete_legacy_missing_excerpts')
        self.assertIsNone(package['packets'][0]['observations'][0]['review_excerpt'])

    def test_legacy_excerpt_is_derived_only_from_recorded_allowlist_markers(self):
        runs=[{'unit_id':'u','experiment_id':'e','attempt_id':'a','run_id':'r','condition_id':'A',
               'scenario_id':'S1','replicate':1,'candidates':[{'candidate_id':'c','payload':{'payload':"1'"},
               'observations':[{'confirmation_index':1,'payload_role':'single','http_status':200,
                   'response_time_ms':9,'response_sha256':'a'*64,
                   'response_indicators':['mysql_syntax_error','mysqli_sql_exception'],
                   'content_markers':[]}]}]}]
        with patch('blind_review.load_runs',return_value=runs):
            packets,_=__import__('blind_review').make_packets(runs)
        observation=packets[0]['observations'][0]
        self.assertEqual(observation['review_excerpt_basis'],'recorded_allowlist_markers')
        self.assertIn('query details redacted',observation['review_excerpt'])
        self.assertNotIn('mysqli_sql_exception',observation['review_excerpt'])

    def test_annotation_import_rejects_missing_ids_and_invalid_labels(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'results/raw') as temp:
            package=Path(temp);(package/'validator').mkdir()
            packets={'scope':'blinded-candidate-review','packets':[{'review_id':'abc'}]}
            raw=(json.dumps(packets,indent=2)+'\n').encode()
            (package/'validator/packets.json').write_bytes(raw)
            import hashlib
            mapping={'abc':{'unit_id':'u','candidate_id':'c'}}
            (package/'mapping.private.json').write_text(json.dumps({'package_sha256':hashlib.sha256(raw).hexdigest(),'mapping':mapping}))
            rows=package/'annotations.csv';rows.write_text('review_id,validator_id,decision,justification\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'cover every review ID'):
                import_annotations(package,rows,'validator-1')
            rows.write_text('review_id,validator_id,decision,justification\nabc,validator-1,maybe,reason\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'valid decision'):
                import_annotations(package,rows,'validator-1')
            rows.write_text('review_id,validator_id,decision,justification\nabc,VAL-01,insufficient_evidence,Only one observation available\n',encoding='utf-8')
            imported=import_annotations(package,rows,'VAL-01')
            self.assertEqual(imported['annotations'][0]['unit_id'],'u')
            self.assertEqual(imported['annotations'][0]['decision'],'insufficient_evidence')


if __name__=='__main__':unittest.main()
