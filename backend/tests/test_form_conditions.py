import unittest
import json
from pathlib import Path
import test_workshop as fixtures
from app.forms.conditions import matches, condition_leaves


class ConditionTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    post = fixtures.WorkshopTest.post

    def test_shared_semantics(self):
        cases = json.loads((Path(__file__).resolve().parents[2] / 'test-fixtures/form-conditions.json').read_text())
        for case in cases:
            self.assertEqual(matches(case['condition'], case['values']), case['expected'], case)

    def test_tree_bounds_structure_and_operands(self):
        leaf = {'field': 'x', 'operator': 'gte', 'value': 1}
        for condition in ({}, {'all': []}, {'any': [leaf] * 11}, {'all': [leaf], 'any': [leaf]},
                          {'all': [{'all': [{'all': [{'all': [leaf]}]}]}]},
                          {'field': 'x', 'operator': 'execute', 'value': 'x'},
                          {'field': 'x', 'operator': [], 'value': 'x'},
                          {'field': 'x', 'operator': 'equals', 'value': 10**1000},
                          {'field': 'x', 'operator': 'gt', 'value': True},
                          {'field': 'x', 'operator': 'contains', 'value': []},
                          {'field': 'x', 'operator': 'equals', 'value': float('inf')},
                          {'all': [{'any': [leaf] * 10}, {'any': [leaf] * 10}]}):
            with self.assertRaises(ValueError): condition_leaves(condition)

    def test_visibility_drives_completion_and_keeps_snapshots(self):
        condition = {'all': [{'field': 'reading', 'operator': 'gte', 'value': 10},
                             {'any': [{'field': 'reading', 'operator': 'lte', 'value': 20}, {'field': 'flag', 'equals': True}]}]}
        fields = [{'key': 'reading', 'label': 'Reading', 'type': 'number'},
                  {'key': 'flag', 'label': 'Flag', 'type': 'checkbox'},
                  {'key': 'reason', 'label': 'Reason', 'type': 'text', 'required': True, 'condition': condition}]
        template = self.c.post('/v2/templates', json={'name': 'Conditions', 'purpose': 'measurement', 'fields': fields})
        self.assertEqual(template.status_code, 201, template.text)
        tid = template.json()['id']
        self.c.post(f'/v2/templates/{tid}/publish')
        flow = self.c.post('/v2/workflows', json={'name': 'Measure', 'stages': [{'key':'measure','name':'Measure','form_phase':'measurement','next':['ready']}, {'key':'ready','name':'Ready','category':'ready'}]}).json()
        job = self.order(stage_forms={'measurement':tid},workflow_id=flow['id'],draft=False)
        path = '/v2/orders/' + job['id']
        job = self.c.patch(path+'/forms/measurement', json={'version':job['version'],'values':{'reading':12}}).json()
        self.assertEqual(self.c.post(path+'/transition', json={'version':job['version'],'target':'ready'}).status_code,422)
        job = self.c.patch(path+'/forms/measurement', json={'version':job['version'],'values':{'reading':25}}).json()
        job = self.post(job, '/transition',target='ready')
        self.assertEqual(job['stage_forms']['measurement']['template']['fields'][2]['condition'],condition)

    def test_reference_and_privacy_validation(self):
        base = [{'key':'secret','label':'Secret','type':'number','read_permission':'finance.read'},
                {'key':'reason','label':'Reason','type':'text','condition':{'all':[{'field':'secret','operator':'gt','value':0}]}}]
        response = self.c.post('/v2/templates',json={'name':'Private','fields':base})
        self.assertEqual(response.status_code,422)
        base[1]['read_permission']='finance.read'
        self.assertEqual(self.c.post('/v2/templates',json={'name':'Private','fields':base}).status_code,201)
        for key in ['missing','reason']:
            base[1]['condition']={'field':key,'equals':True}
            self.assertEqual(self.c.post('/v2/templates',json={'name':'Bad reference','fields':base}).status_code,422)
