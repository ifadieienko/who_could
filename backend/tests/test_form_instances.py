"""Instance persistence, compatibility, snapshots and access boundaries."""
import json
import io
import zipfile
import unittest
from datetime import timedelta
from unittest.mock import patch
import test_workshop as fixtures
from sqlalchemy import select
from app.database import db, engine
from app.repair_access import utc
from app.repair_models import JobFormInstance, RepairOrder, FormTemplate, WorkshopRole, Workshop


class FormInstanceTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    member = fixtures.WorkshopTest.member

    def setup_form(self):
        response = self.c.post('/v2/templates', json={
            'name': 'Measurements', 'purpose': 'measurement', 'fields': [
                {'key': 'reading', 'label': 'Reading', 'type': 'number'},
                {'key': 'secret', 'label': 'Private', 'type': 'text',
                 'read_permission': 'finance.read', 'write_permission': 'finance.write'},
            ],
        })
        self.assertEqual(response.status_code, 201, response.text)
        template = response.json()
        self.assertEqual(self.c.post(f"/v2/templates/{template['id']}/publish").status_code, 200)
        job = self.order(stage_forms={'measurement': template['id']})
        path = '/v2/jobs/' + job['id'] + '/forms'
        return job, template, path

    def save(self, path, page, values, client=None):
        return (client or self.c).patch(path + '/measurement', json={
            'job_version': page['job_version'], 'version': page['items'][0]['version'], 'values': values,
        })

    def test_independent_version_and_both_api_contracts(self):
        job, template, path = self.setup_form()
        page = self.c.get(path).json()
        instance = page['items'][0]
        self.assertEqual((instance['version'], instance['form_revision']), (1, 1))
        self.assertEqual(instance['schema_snapshot'], job['stage_forms']['measurement']['template'])
        with db() as session:
            self.assertEqual(instance['form_template_family'], session.get(FormTemplate, template['id']).family)
        response = self.save(path, page, {'reading': 0, 'secret': 'confidential'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['form']['version'], 2)
        legacy = self.c.get('/v2/orders/' + job['id']).json()
        self.assertEqual(legacy['stage_forms']['measurement']['values'], {'reading': 0, 'secret': 'confidential'})
        page = self.c.get(path).json()
        response = self.c.patch('/v2/orders/' + job['id'] + '/forms/measurement', json={
            'version': page['job_version'], 'values': {'reading': 2.5},
        })
        self.assertEqual(response.status_code, 200, response.text)
        page = self.c.get(path).json()
        self.assertEqual(page['items'][0]['values']['reading'], 2.5)
        self.assertEqual(page['items'][0]['version'], 3)
        # No-op form saves and unrelated job edits do not invent form revisions.
        self.assertEqual(self.save(path, page, {'reading': 2.5}).json()['form']['version'], 3)
        page = self.c.get(path).json()
        self.c.patch('/v2/jobs/' + job['id'], json={'version': page['job_version'], 'priority': 'high'})
        self.assertEqual(self.c.get(path).json()['items'][0]['version'], 3)

    def test_conflicts_validation_and_atomicity(self):
        job, _, path = self.setup_form()
        page = self.c.get(path).json()
        self.assertEqual(self.save(path, page, {'reading': 4}).status_code, 200)
        self.assertEqual(self.save(path, page, {'reading': 5}).status_code, 409)
        latest = self.c.get(path).json()
        stale_form = {**latest, 'items': page['items']}
        self.assertEqual(self.save(path, stale_form, {'reading': 6}).status_code, 409)
        for values in ({'reading': 'invalid'}, {'unknown': 1}, {'reading': True}):
            self.assertEqual(self.save(path, latest, values).status_code, 422)
        self.assertEqual(self.c.get(path).json(), latest)
        payload = {'job_version': latest['job_version'], 'version': 1, 'values': {}}
        self.assertEqual(self.c.patch(path + '/missing', json=payload).status_code, 404)
        self.assertEqual(self.c.patch(path + '/intake', json=payload).status_code, 422)
        self.assertEqual(self.c.patch(path + '/measurement', json={**payload, 'schema_snapshot': {}}).status_code, 422)
        with db() as s:
            s.scalar(select(RepairOrder).where(RepairOrder.public_id == job['id'])).status = 'cancelled'
        self.assertEqual(self.save(path, latest, {'reading': 7}).status_code, 409)
        self.assertEqual(self.c.get(path).json(), latest)

    def test_scope_field_permissions_and_billing(self):
        job, _, path = self.setup_form()
        page = self.c.get(path).json()
        self.assertEqual(self.save(path, page, {'secret': 'Hidden amount'}).status_code, 200)
        other, _ = self.register('foreign-instance@example.com')
        latest = self.c.get(path).json()
        self.assertEqual(other.get(path).status_code, 404)
        self.assertEqual(self.save(path, latest, {}, other).status_code, 404)
        employee, _, role = self.member()
        response = employee.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Hidden amount', response.text)
        self.assertNotIn('secret', response.text)
        self.assertEqual(self.save(path, latest, {'secret': 'Changed'}, employee).status_code, 403)
        with db() as s:
            s.get(WorkshopRole, role).permissions = ['jobs.read']
        self.assertEqual(self.save(path, latest, {'reading': 8}, employee).status_code, 403)
        with db() as s:
            s.get(WorkshopRole, role).permissions = ['jobs.read', 'jobs.edit']
            s.scalar(select(RepairOrder).where(RepairOrder.public_id == job['id'])).assigned_to = self.c.get('/me').json()['id']
        self.assertEqual(employee.get(path).status_code, 404)
        self.assertEqual(self.save(path, latest, {}, employee).status_code, 404)
        with db() as s:
            s.get(Workshop, self.shop['id']).trial_until = utc() - timedelta(days=10)
        with patch.dict('os.environ', {'BILLING_ENFORCED': 'true'}):
            self.assertEqual(self.save(path, latest, {'reading': 9}).status_code, 402)
        self.assertEqual(self.c.get(path).json(), latest)

    def test_snapshot_warranty_and_export(self):
        job, template, path = self.setup_form()
        page = self.c.get(path).json()
        self.save(path, page, {'reading': 10})
        original = self.c.get(path).json()['items'][0]
        # Even mutable/deleted template metadata cannot replace a frozen schema.
        with db() as s:
            t = s.get(FormTemplate, template['id'])
            t.fields = []
            t.revision = 8
            t.archived = True
            s.scalar(select(RepairOrder).where(RepairOrder.public_id == job['id'])).status = 'issued'
        self.assertEqual(self.c.get(path).json()['items'][0], original)
        latest = self.c.get(path).json()
        response = self.c.post('/v2/orders/' + job['id'] + '/warranty', json={
            'version': latest['job_version'], 'text': 'Inspect again',
        })
        self.assertEqual(response.status_code, 201, response.text)
        warranty = self.c.get('/v2/jobs/' + response.json()['id'] + '/forms').json()['items'][0]
        self.assertNotEqual(warranty['id'], original['id'])
        self.assertEqual(warranty['schema_snapshot'], original['schema_snapshot'])
        self.assertEqual((warranty['form_revision'], warranty['version']), (1, 1))
        self.assertTrue(all(v is None for v in warranty['values'].values()))
        export = self.c.get('/v2/export')
        self.assertEqual(export.status_code, 200, export.text if export.status_code != 200 else '')
        with zipfile.ZipFile(io.BytesIO(export.content)) as z:
            data = json.loads(z.read('workshop.json'))
        self.assertEqual(len(data['job_form_instances']), 2)
        self.assertEqual(data['job_form_instances'][0]['schema_snapshot'], original['schema_snapshot'])

    def test_failed_job_creation_does_not_leave_instances(self):
        _, template, _ = self.setup_form()
        with db() as s:
            before = len(s.scalars(select(JobFormInstance)).all())
        response = self.c.post('/v2/orders', json={
            'template_id': self.t['id'], 'workflow_id': self.w['id'],
            'customer': {'name': 'Failed'}, 'model': 'Device', 'problem': 'Problem',
            'stage_forms': {'measurement': template['id']}, 'values': {'invalid': 'field'},
        })
        self.assertEqual(response.status_code, 422)
        with db() as s:
            self.assertEqual(len(s.scalars(select(JobFormInstance)).all()), before)


    @unittest.skipUnless(engine.dialect.name in {'mysql', 'mariadb'}, 'Requires MariaDB row locks')
    def test_concurrent_legacy_and_generic_writes_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from fastapi.testclient import TestClient
        job, _, path = self.setup_form()
        page = self.c.get(path).json()
        barrier = Barrier(2)
        def save(generic):
            client = TestClient(fixtures.app)
            client.cookies.update(self.c.cookies)
            client.headers.update(self.c.headers)
            barrier.wait(timeout=10)
            if generic:
                return self.save(path, page, {'reading': 101}, client)
            return client.patch('/v2/orders/' + job['id'] + '/forms/measurement', json={
                'version': page['job_version'], 'values': {'reading': 202},
            })
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(save, [True, False]))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        after = self.c.get(path).json()
        self.assertEqual(after['items'][0]['version'], 2)
        self.assertEqual(after['job_version'], page['job_version'] + 1)
        legacy = self.c.get('/v2/orders/' + job['id']).json()
        self.assertEqual(legacy['stage_forms']['measurement']['values']['reading'], after['items'][0]['values']['reading'])
