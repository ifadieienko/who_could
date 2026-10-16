import unittest
from copy import deepcopy
import test_workshop as fixtures
from app.database import db
from app.repair_models import FormTemplate


TABLE = {"key": "measurements", "label": "Measurements", "type": "table", "required": True,
         "min_rows": 1, "max_rows": 3, "columns": [
             {"key": "reading", "label": "Reading", "type": "number", "required": True, "min": -10, "max": 10, "precision": 2, "unit": "mm"},
             {"key": "result", "label": "Result", "type": "select", "options": ["Pass", "Fail"], "required": True},
             {"key": "note", "label": "Note", "type": "text"},
             {"key": "checked", "label": "Checked", "type": "checkbox"},
             {"key": "date", "label": "Date", "type": "date"},
         ]}


class TableFormTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    member = fixtures.WorkshopTest.member
    post = fixtures.WorkshopTest.post

    def template(self, field=None, purpose='measurement'):
        response = self.c.post('/v2/templates', json={'name': 'Measurements', 'purpose': purpose, 'fields': [field or TABLE]})
        self.assertEqual(response.status_code, 201, response.text)
        template = response.json()
        self.assertEqual(self.c.post(f"/v2/templates/{template['id']}/publish").status_code, 200)
        return template

    def setup_job(self, field=None):
        template = self.template(field)
        workflow = self.c.post('/v2/workflows', json={'name': 'Measure', 'stages': [
            {'key': 'measure', 'name': 'Measure', 'form_phase': 'measurement', 'next': ['ready']},
            {'key': 'ready', 'name': 'Ready', 'category': 'ready'},
        ]}).json()
        return self.order(workflow_id=workflow['id'], stage_forms={'measurement': template['id']}, draft=False), template

    def save(self, job, rows, client=None):
        return (client or self.c).patch('/v2/orders/' + job['id'] + '/forms/measurement', json={'version': job['version'], 'values': {'measurements': rows}})

    def test_drafts_completion_snapshot_receipt_and_print(self):
        job, template = self.setup_job()
        # Draft rows can be incomplete, but completing the stage cannot.
        response = self.save(job, [{'reading': 0}])
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()
        path = '/v2/orders/' + job['id']
        self.assertEqual(self.c.post(path + '/transition', json={'version': job['version'], 'target': 'ready'}).status_code, 422)
        rows = [{'reading': 0, 'result': 'Pass', 'note': '<script>bad</script>', 'checked': False, 'date': '2026-10-16'}]
        response = self.save(job, rows)
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()
        with db() as s:
            s.get(FormTemplate, template['id']).fields = []
        job = self.post(job, '/transition', target='ready')
        job = self.post(job, '/issue', receiver='Customer')
        self.assertEqual(job['receipt']['stage_forms']['measurement']['values']['measurements'], rows)
        printed = self.c.get(path + '/document?kind=issue')
        self.assertEqual(printed.status_code, 200, printed.text)
        self.assertIn('<table class="form-table">', printed.text)
        self.assertIn('Reading · mm', printed.text)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', printed.text)
        self.assertNotIn('<script>bad</script>', printed.text)
        self.assertEqual(self.save(job, []).status_code, 409)

    def test_invalid_rows_are_atomic_and_type_safe(self):
        job, _ = self.setup_job()
        baseline = self.save(job, [{'reading': 1, 'result': 'Pass'}]).json()
        for rows in ({}, 'text', [None], [{'unknown': 1}], [{}] * 4,
                     [{'reading': True}], [{'reading': 11}], [{'reading': -11}],
                     [{'reading': 1.123}], [{'reading': '1'}], [{'result': 'Unknown'}],
                     [{'date': '2026-02-30'}], [{'checked': 1}], [{'note': 'x' * 1001}]):
            response = self.save(baseline, rows)
            self.assertEqual(response.status_code, 422, response.text)
        after = self.c.get('/v2/orders/' + job['id']).json()
        self.assertEqual(after['version'], baseline['version'])
        self.assertEqual(after['stage_forms'], baseline['stage_forms'])
        for rows in ([], None):
            edited = self.save(baseline, rows)
            self.assertEqual(edited.status_code, 200, edited.text)
            baseline = edited.json()
            self.assertEqual(self.c.post('/v2/orders/' + job['id'] + '/transition', json={'version': baseline['version'], 'target': 'ready'}).status_code, 422)

    def test_template_limits_and_no_nested_or_column_permissions(self):
        invalid = [dict(TABLE, columns=[]), dict(TABLE, columns=TABLE['columns'] * 3),
                   dict(TABLE, min_rows=4), dict(TABLE, max_rows=101)]
        for column in ({'type': 'table'}, {'read_permission': 'finance.read'}, {'min': 3, 'max': 2}, {'precision': 11}, {'type': 'text', 'precision': 2}):
            field = deepcopy(TABLE)
            field['columns'][0].update(column)
            invalid.append(field)
        for field in invalid:
            response = self.c.post('/v2/templates', json={'name': 'Invalid', 'fields': [field]})
            self.assertEqual(response.status_code, 422, response.text)

    def test_table_privacy_audit_and_tenant_isolation(self):
        field = {**TABLE, 'read_permission': 'finance.read', 'write_permission': 'finance.write'}
        job, _ = self.setup_job(field)
        job = self.save(job, [{'reading': 3, 'result': 'Pass', 'note': 'secret-table-value'}]).json()
        employee, _, _ = self.member()
        for suffix in ('', '/events'):
            self.assertNotIn('secret-table-value', employee.get('/v2/orders/' + job['id'] + suffix).text)
        self.assertNotIn('measurements', employee.get('/v2/jobs/' + job['id'] + '/forms').text)
        self.assertEqual(self.save(job, [{'reading': 4}], employee).status_code, 403)
        other, _ = self.register('table-foreign@example.com')
        self.assertEqual(self.save(job, [], other).status_code, 404)

    def test_required_intake_table_and_frozen_print(self):
        template = self.template(purpose='intake')
        workflow = self.c.post('/v2/workflows', json={'name': 'Simple intake', 'stages': [{'key': 'received', 'name': 'Received', 'next': ['ready']}, {'key': 'ready', 'name': 'Ready', 'category': 'ready'}]}).json()
        job = self.order(template_id=template['id'], workflow_id=workflow['id'])
        path = '/v2/orders/' + job['id']
        self.assertEqual(self.c.post(path + '/accept', json={'version': job['version']}).status_code, 422)
        response = self.c.patch(path, json={'version': job['version'], 'values': {'measurements': [{'reading': 2.25, 'result': 'Pass'}]}})
        self.assertEqual(response.status_code, 200, response.text)
        job = self.post(response.json(), '/accept')
        response = self.c.patch(path, json={'version': job['version'], 'values': {'measurements': [{'reading': 9, 'result': 'Fail'}]}})
        self.assertEqual(response.status_code, 200, response.text)
        printed = self.c.get(path + '/document?kind=intake')
        self.assertIn('2.25', printed.text)
        self.assertNotIn('Fail', printed.text)
