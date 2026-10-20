import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dvwa'))
from aggregate_metrics import aggregate


def fixture_dataset():
    runs=[];annotations=[]
    for condition in ('B','C'):
        for scenario_index in range(1,10):
            for rep in (1,2,3):
                unit=f'{condition}-S{scenario_index}-r{rep}'
                candidates=[]
                for n,success in enumerate((True,False),1):
                    cid=f'{unit}-c{n}'
                    candidates.append({'candidate_id':cid,'confirmed_success':success,
                                       'evidence_status':'CONSISTENT_POSITIVE' if success else 'CONSISTENT_NEGATIVE'})
                    annotations.append({'unit_id':unit,'candidate_id':cid,
                                        'decision':'success' if success else 'failure'})
                runs.append({'unit_id':unit,'experiment_id':'fixture','scenario_id':f'S{scenario_index}',
                             'condition_id':condition,'replicate':rep,'status':'completed',
                             'metric_eligible':True,'candidates':candidates,
                             'analysis_summary':{'binary_decision_eligible':True,
                                 'system_decision':'positive' if scenario_index==1 else 'negative'}})
    for condition in ('A',):
        for scenario_index in range(1,10):
            for rep in (1,2,3):
                runs.append({'unit_id':f'{condition}-S{scenario_index}-r{rep}','experiment_id':'fixture',
                    'scenario_id':f'S{scenario_index}','condition_id':condition,'replicate':rep,
                    'status':'completed','metric_eligible':True,'candidates':[],
                    'analysis_summary':{'binary_decision_eligible':True,
                        'system_decision':'positive' if scenario_index==1 else 'negative'}})
    for condition in ('A','B'):
        for scenario_index in (10,11,12):
            for rep in (1,2,3):
                positive=scenario_index==10
                runs.append({'unit_id':f'{condition}-S{scenario_index}-r{rep}','experiment_id':'fixture',
                    'scenario_id':f'S{scenario_index}','condition_id':condition,'replicate':rep,
                    'status':'completed','metric_eligible':True,'candidates':[],
                    'analysis_summary':{'binary_decision_eligible':True,
                                        'system_decision':'positive' if positive else 'negative'}})
    return runs,annotations


class AggregateMetricsTests(unittest.TestCase):
    def test_per_run_psr_fpr_and_sample_standard_deviation(self):
        runs,annotations=fixture_dataset()
        result=aggregate(runs,annotations,experiment_id='fixture')
        self.assertTrue(result['psr']['eligible'])
        self.assertTrue(result['fpr']['eligible'])
        for row in result['psr']['summary']:
            self.assertEqual(row['mean'],.5)
            self.assertEqual(row['sample_sd'],0)
        for row in result['fpr']['summary']:
            self.assertAlmostEqual(row['mean'],1/3)
            self.assertEqual(row['sample_sd'],0)
            self.assertEqual(row['n'],3)
        confusion=result['system_confusion']['condition_replicates'][0]
        self.assertEqual((confusion['TP'],confusion['FN'],confusion['FP'],confusion['TN']),(1,8,1,2))

    def test_missing_validator_record_withholds_psr_but_keeps_valid_run_audit(self):
        runs,annotations=fixture_dataset()
        annotations.pop()
        result=aggregate(runs,annotations)
        self.assertFalse(result['psr']['eligible'])
        self.assertFalse(result['annotations_complete'])
        self.assertTrue(result['fpr']['eligible'])

    def test_validator_success_requires_three_of_three_executor_evidence(self):
        runs,annotations=fixture_dataset()
        runs[0]['candidates'][0]['confirmed_success']=False
        result=aggregate(runs,annotations)
        row=next(x for x in result['psr']['per_run'] if x['unit_id']==runs[0]['unit_id'])
        self.assertEqual(row['success_count'],0)

    def test_success_claim_conflicts_with_mixed_executor_evidence_and_is_not_counted(self):
        runs,annotations=fixture_dataset()
        run=next(r for r in runs if r['condition_id']=='B' and r['scenario_id']=='S1' and r['replicate']==1)
        run['candidates'][0].update(confirmed_success=True,evidence_status='MIXED_EVIDENCE')
        row=next(x for x in aggregate(runs,annotations)['psr']['per_run'] if x['unit_id']==run['unit_id'])
        self.assertEqual(row['success_count'],0)

    def test_fpr_withholds_primary_when_a_negative_run_abstains(self):
        runs,annotations=fixture_dataset()
        next(r for r in runs if r['condition_id']=='A' and r['scenario_id']=='S12' and r['replicate']==2)['analysis_summary']['binary_decision_eligible']=False
        result=aggregate(runs,annotations)
        self.assertFalse(result['fpr']['eligible'])
        row=next(x for x in result['fpr']['condition_replicates'] if x['condition_id']=='A' and x['replicate']==2)
        self.assertIsNone(row['fpr'])
        self.assertIn('S12',row['unresolved_scenarios'])
        self.assertEqual(row['reason'],'planned_negative_missing_invalid_or_abstained')

    def test_validator_rejection_does_not_filter_a_system_false_positive(self):
        runs,annotations=fixture_dataset()
        baseline=aggregate(runs,annotations)
        annotations[0]['decision']='failure'
        result=aggregate(runs,annotations)
        row=next(x for x in result['fpr']['condition_replicates'] if x['condition_id']=='A' and x['replicate']==1)
        original=next(x for x in baseline['fpr']['condition_replicates'] if x['condition_id']=='A' and x['replicate']==1)
        self.assertEqual((row['FP'],row['TN'],row['fpr']),(1,2,1/3))
        self.assertEqual(row['fpr'],original['fpr'])

    def test_mixed_evidence_stays_in_psr_denominator_and_not_numerator(self):
        runs,annotations=fixture_dataset()
        run=next(r for r in runs if r['condition_id']=='B' and r['scenario_id']=='S1' and r['replicate']==1)
        run['candidates'][0].update(confirmed_success=False,evidence_status='MIXED_EVIDENCE')
        row=next(x for x in aggregate(runs,annotations)['psr']['per_run'] if x['unit_id']==run['unit_id'])
        self.assertEqual((row['success_count'],row['valid_candidates'],row['psr']),(0,2,0))

    def test_incomplete_budget_is_reported_and_excluded_from_psr(self):
        runs,annotations=fixture_dataset()
        run=next(r for r in runs if r['condition_id']=='B' and r['scenario_id']=='S2' and r['replicate']==1)
        run.update(metric_eligible=False,status='excluded')
        row=next(x for x in aggregate(runs,annotations)['psr']['per_run'] if x['unit_id']==run['unit_id'])
        self.assertFalse(row['eligible'])
        self.assertEqual(row['reason'],'run_status_excluded')

    def test_invalid_or_incomplete_planned_negative_is_not_treated_as_tn(self):
        runs,annotations=fixture_dataset()
        target=next(r for r in runs if r['condition_id']=='A' and r['scenario_id']=='S11' and r['replicate']==3)
        target.update(metric_eligible=False,status='excluded')
        result=aggregate(runs,annotations)
        row=next(x for x in result['fpr']['condition_replicates'] if x['condition_id']=='A' and x['replicate']==3)
        self.assertFalse(row['eligible'])
        self.assertIsNone(row['fpr'])
        self.assertEqual(row['decision_coverage'],2/3)
        confusion=next(x for x in result['system_confusion']['condition_replicates'] if x['condition_id']=='A' and x['replicate']==3)
        self.assertEqual(confusion['decision_coverage'],11/12)

    def test_zero_resolved_negative_denominator_is_undefined(self):
        runs,annotations=fixture_dataset()
        for run in runs:
            if run['condition_id']=='A' and run['scenario_id'] in {'S10','S11','S12'} and run['replicate']==1:
                run['analysis_summary']['system_decision']='inconclusive'
        result=aggregate(runs,annotations)
        row=next(x for x in result['fpr']['condition_replicates'] if x['condition_id']=='A' and x['replicate']==1)
        self.assertEqual(row['FP']+row['TN'],0)
        self.assertIsNone(row['fpr'])

    def test_csv_flattening_preserves_metric_rows_and_traceability(self):
        from aggregate_metrics import csv_rows
        runs,annotations=fixture_dataset()
        columns,rows=csv_rows(aggregate(runs,annotations))
        self.assertIn('unit_id',columns)
        self.assertTrue(any(r['metric']=='PSR' and r['row_type']=='run' and r['unit_id'] for r in rows))
        confusion=next(r for r in rows if r['metric']=='system_confusion' and r['row_type']=='replicate')
        self.assertEqual((confusion['TP'],confusion['FN'],confusion['FP'],confusion['TN']),(1,8,1,2))

    def test_duplicate_runs_and_orphan_annotations_are_rejected(self):
        runs,annotations=fixture_dataset()
        with self.assertRaisesRegex(ValueError,'Duplicate condition-run'):
            aggregate(runs+[runs[0]],annotations)
        orphan={**annotations[0],'candidate_id':'not-in-ledger'}
        with self.assertRaisesRegex(ValueError,'unknown candidate'):
            aggregate(runs,annotations+[orphan])


if __name__=='__main__':unittest.main()
