"""Checks for fabricated observations, invalid arithmetic and archive corruption."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from .engine import FIELDS, evaluate, extract_value, parse_reply
from .replay import replay


def fixture():
    fields={k:{'value':v[0] if isinstance(v,list) else 4,'evidence':[]} for k,v in FIELDS.items()}
    index={'s1':2,'s2':1,'s3':1,'s4':0,'y1':1,'y2':1,'y3':0,'y4':0}
    records=[{'id':str(i),'score':{'ref':f's{i}'},'truth':{'ref':f'y{i}'}} for i in range(1,5)]
    contract={'fields':fields,'headline':{'metric':'auc','reported':.875,'score_direction':'higher','records':records}}
    return contract,index


class ContractChecks(unittest.TestCase):
    def test_auc_ties(self):
        contract,index=fixture()
        result=evaluate(contract,index,{'metric':'auc','reported':.875,'n':4,'tolerance':0})
        self.assertTrue(result['matched'])
        self.assertEqual(result['computed'],.875)

    def test_score_and_truth_need_independent_cells(self):
        contract,index=fixture()
        for record in contract['headline']['records']:record['score']={'calc':'multiply','args':[{'ref':record['truth']['ref']},1]}
        result=evaluate(contract,index,{'metric':'auc','reported':.875,'n':4,'tolerance':1})
        self.assertFalse(result['matched'])
        self.assertEqual(sum('same source cell' in error for error in result['errors']),4)

    def test_aggregate_count_cannot_stand_for_many_units(self):
        contract,index=fixture()
        index['count']=2
        for record in contract['headline']['records'][:2]:record['score']={'ref':'count'}
        result=evaluate(contract,index,{'metric':'auc','reported':.875,'n':4,'tolerance':1})
        self.assertFalse(result['matched'])
        self.assertEqual(sum('same source cells' in error for error in result['errors']),1)

    def test_label_means_the_same_for_every_unit(self):
        contract,index=fixture()
        for i,record in enumerate(contract['headline']['records'],1):
            index[f'o{i}']='Progressive Disease';record['truth']={'ref':f'o{i}','map':{'Progressive Disease':index[f'y{i}']}}
        result=evaluate(contract,index,{'metric':'auc','reported':.875,'n':4,'tolerance':1})
        self.assertFalse(result['matched'])
        self.assertTrue(any('must mean the same' in error for error in result['errors']))

    def test_shared_count_is_not_an_outcome(self):
        contract,index=fixture()
        index['p13']='Of the 6 patients, 5 were treated with at least one drug'
        for record in contract['headline']['records'][:2]:
            record['truth']={'ref':'p13','regex':r'(\d) were treated','threshold':4,'op':'>'}
        result=evaluate(contract,index,{'metric':'auc','reported':.875,'n':4,'tolerance':1})
        self.assertFalse(result['matched'])
        self.assertEqual(sum('shared count is an aggregate' in error for error in result['errors']),1)

    def test_literal_observation_rejected(self):
        with self.assertRaisesRegex(ValueError,'source references'):
            extract_value(.875,{})

    def test_duplicate_units_rejected(self):
        contract,index=fixture();contract['headline']['records'][1]['id']='1'
        self.assertFalse(evaluate(contract,index)['matched'])

    def test_frozen_denominator_rejects_self_selected_subset(self):
        contract,index=fixture()
        result=evaluate(contract,index,{'metric':'auc','reported':.875,'n':5,'tolerance':0})
        self.assertFalse(result['matched'])
        self.assertIn('Expected 5 analysis units, got 4',result['errors'])

    def test_invalid_regex_becomes_a_diagnostic(self):
        contract,index=fixture();contract['headline']['records'][0]['score']['regex']='('
        self.assertFalse(evaluate(contract,index)['matched'])

    def test_censored_auc_rejected(self):
        contract,index=fixture();index['s1']='>2'
        contract['headline']['records'][0]['score']['censor']='above_cutoff'
        result=evaluate(contract,index)
        self.assertFalse(result['matched'])
        self.assertTrue(any('interval-aware' in s for s in result['errors']))

    def test_ambiguous_censor_threshold_rejected(self):
        contract,index=fixture();index['s1']='>1'
        contract['headline'].update(metric='accuracy',reported=1,threshold=2,op='>')
        contract['headline']['records'][0]['score']['censor']='above_cutoff'
        self.assertTrue(any('crosses' in s for s in evaluate(contract,index)['errors']))

    def test_nonstandard_json_rejected(self):
        with self.assertRaisesRegex(ValueError,'Nonstandard'):
            parse_reply('{"value": NaN}')

    def test_archive_tamper_is_detected_before_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'gold.json').write_text('{}')
            digest=hashlib.sha256((root/'gold.json').read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps({'papers':[],'files':{'gold.json':digest}}))
            (root/'gold.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'Archive hash mismatch'):
                replay(root)


if __name__=='__main__':unittest.main()
