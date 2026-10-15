"""Generic reads must preserve the same permissions and identity as repairs."""
import unittest
import test_workshop as fixtures
from app.database import db
from app.jobs.models import Job
from app.repair_models import WorkshopRole, RepairEvent
from sqlalchemy import select


class JobReadTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    member = fixtures.WorkshopTest.member

    def test_existing_order_identity_and_snapshots(self):
        created = self.order()
        # Compare persisted reads: MariaDB DATETIME truncates creation microseconds.
        original = self.c.get('/v2/orders/' + created['id']).json()
        response = self.c.get('/v2/jobs/' + original['id'])
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()
        expected = dict(original)
        expected['organization_id'] = self.shop['id']
        expected['asset_id'] = expected.pop('device_id')
        expected['description'] = expected.pop('problem')
        expected.update(vertical_key='repair', job_type='repair', priority='normal', site_id=None)
        self.assertEqual(job, expected)
        self.assertEqual(self.c.get('/v2/orders/' + original['id']).json(), original)

    def test_cursor_and_filters(self):
        first, second, third = self.order(), self.order(), self.order()
        page = self.c.get('/v2/jobs', params={'limit': 2}).json()
        self.assertEqual([x['id'] for x in page['items']], [first['id'], second['id']])
        tail = self.c.get('/v2/jobs', params={'limit': 2, 'after': page['next']}).json()
        self.assertEqual([x['id'] for x in tail['items']], [third['id']])
        self.assertIsNone(tail['next'])
        for key, value in [('asset_id', first['device_id']), ('customer_id', first['customer_id'])]:
            result = self.c.get('/v2/jobs', params={key: value}).json()
            self.assertEqual([x['id'] for x in result['items']], [first['id']])
        self.assertEqual(self.c.get('/v2/jobs?status=issued').json()['items'], [])
        for query in ('limit=101', 'limit=0', 'after=-1', 'asset_id=0'):
            self.assertEqual(self.c.get('/v2/jobs?' + query).status_code, 422)

    def test_other_organization_cannot_read_any_job_resource(self):
        original = self.order()
        other, _ = self.register('other-jobs@example.com')
        self.assertEqual(other.get('/v2/jobs').json()['items'], [])
        for suffix in ('', '/events', '/attachments'):
            self.assertEqual(other.get('/v2/jobs/' + original['id'] + suffix).status_code, 404)
        self.assertEqual(other.get('/v2/jobs', params={'asset_id': original['device_id']}).json()['items'], [])

    def test_generic_permission_own_scope_and_finance_redaction(self):
        visible, hidden = self.order(), self.order()
        employee, uid, role_id = self.member()
        with db() as s:
            s.get(WorkshopRole, role_id).permissions = ['jobs.read']
            record = s.scalar(select(Job).where(Job.public_id == hidden['id']))
            record.assigned_to = self.c.get('/me').json()['id']
            record = s.scalar(select(Job).where(Job.public_id == visible['id']))
            s.add(RepairEvent(workshop_id=self.shop['id'], order_id=record.id, kind='estimate.created', data={'secret': 'price'}))
        self.assertEqual([x['id'] for x in employee.get('/v2/jobs').json()['items']], [visible['id']])
        for suffix in ('', '/events', '/attachments'):
            self.assertEqual(employee.get('/v2/jobs/' + hidden['id'] + suffix).status_code, 404)
        data = employee.get('/v2/jobs/' + visible['id']).json()
        self.assertIsNone(data['customer'])
        self.assertNotIn('estimates', data)
        events = employee.get('/v2/jobs/' + visible['id'] + '/events').json()['items']
        self.assertFalse(any(x['kind'].startswith('estimate') for x in events))
        self.assertEqual(employee.get('/v2/jobs', params={'customer_id': visible['customer_id']}).status_code, 403)
        with db() as s:
            s.get(WorkshopRole, role_id).permissions = []
        for path in ('/v2/jobs', '/v2/jobs/' + visible['id'], '/v2/jobs/' + visible['id'] + '/events', '/v2/jobs/' + visible['id'] + '/attachments'):
            self.assertEqual(employee.get(path).status_code, 403)

    def test_event_cursor_matches_compatibility_api(self):
        original = self.order()
        with db() as s:
            record = s.scalar(select(Job).where(Job.public_id == original['id']))
            for i in range(35):
                s.add(RepairEvent(workshop_id=self.shop['id'], order_id=record.id, kind='note', data={'text': str(i)}))
        for suffix in ('/events', '/attachments'):
            new = self.c.get('/v2/jobs/' + original['id'] + suffix).json()
            old = self.c.get('/v2/orders/' + original['id'] + suffix).json()
            self.assertEqual(new, old)
            if new['next']:
                next_page = self.c.get('/v2/jobs/' + original['id'] + suffix, params={'before': new['next']}).json()
                self.assertFalse({x['id'] for x in new['items']} & {x['id'] for x in next_page['items']})

    def job_payload(self, **updates):
        original = self.order()
        return {
            'customer_id': original['customer_id'],
            'asset_id': original['device_id'],
            'template_id': self.t['id'],
            'workflow_id': self.w['id'],
            'description': 'Inspect customer asset',
            'job_type': 'inspection',
            'priority': 'high',
            **updates,
        }

    def test_generic_create_edit_and_legacy_compatibility(self):
        payload = self.job_payload()
        site = self.c.post('/v2/sites', json={'customer_id': payload['customer_id'], 'name': 'Lab'}).json()
        response = self.c.post('/v2/jobs', json={**payload, 'site_id': site['id']})
        self.assertEqual(response.status_code, 201, response.text)
        job = response.json()
        self.assertEqual((job['job_type'], job['priority'], job['site_id']), ('inspection', 'high', site['id']))
        legacy = self.c.get('/v2/orders/' + job['id']).json()
        self.assertEqual(legacy['device_id'], payload['asset_id'])
        self.assertEqual(legacy['problem'], payload['description'])
        changed = self.c.patch('/v2/jobs/' + job['id'], json={
            'version': job['version'], 'description': 'Revised inspection',
            'priority': 'urgent', 'site_id': None,
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        changed = changed.json()
        self.assertEqual(changed['version'], job['version'] + 1)
        self.assertEqual((changed['description'], changed['priority'], changed['site_id']), ('Revised inspection', 'urgent', None))
        event = next(e for e in changed['events'] if e['kind'] == 'order.edited')
        self.assertEqual(event['data']['metadata_changes']['site_id'], {'before': site['id'], 'after': None})
        self.assertEqual(self.c.patch('/v2/jobs/' + job['id'], json={'version': job['version'], 'priority': 'low'}).status_code, 409)
        edited_legacy = self.c.patch('/v2/orders/' + job['id'], json={'version': changed['version'], 'problem': 'Legacy edit'})
        self.assertEqual(edited_legacy.status_code, 200, edited_legacy.text)
        after = self.c.get('/v2/jobs/' + job['id']).json()
        self.assertEqual((after['description'], after['priority'], after['job_type']), ('Legacy edit', 'urgent', 'inspection'))

    def test_job_relations_are_validated_and_failed_creates_are_atomic(self):
        payload = self.job_payload()
        second = self.order()
        wrong_site = self.c.post('/v2/sites', json={'customer_id': second['customer_id'], 'name': 'Other customer'}).json()
        other, _ = self.register('foreign-job@example.com')
        foreign_customer = other.post('/v2/customer-records', json={'name': 'Foreign'}).json()
        foreign_site = other.post('/v2/sites', json={'customer_id': foreign_customer['id'], 'name': 'Foreign site'}).json()
        foreign_asset = other.post('/v2/assets', json={'customer_id': foreign_customer['id'], 'name': 'Foreign asset'}).json()
        before = self.c.get('/v2/jobs').json()
        for changes, status in [({'site_id': wrong_site['id']}, 422), ({'site_id': foreign_site['id']}, 404), ({'asset_id': second['device_id']}, 422), ({'asset_id': foreign_asset['id']}, 404), ({'customer_id': foreign_customer['id']}, 404)]:
            result = self.c.post('/v2/jobs', json={**payload, **changes})
            self.assertEqual(result.status_code, status, result.text)
        self.assertEqual(self.c.get('/v2/jobs').json(), before)
        job = self.c.post('/v2/jobs', json=payload).json()
        for site, status in [(wrong_site, 422), (foreign_site, 404)]:
            result = self.c.patch('/v2/jobs/' + job['id'], json={'version': job['version'], 'site_id': site['id'], 'priority': 'urgent'})
            self.assertEqual(result.status_code, status, result.text)
        unchanged = self.c.get('/v2/jobs/' + job['id']).json()
        self.assertEqual((unchanged['version'], unchanged['priority'], unchanged['site_id']), (job['version'], 'high', None))
        self.assertEqual(other.patch('/v2/jobs/' + job['id'], json={'version': job['version'], 'priority': 'low'}).status_code, 404)

    def test_generic_write_validation_and_immutable_metadata(self):
        payload = self.job_payload()
        for changes in ({'asset_id': None}, {'priority': 'unknown'}, {'job_type': 'bad type'}, {'vertical_key': 'calibration'}, {'description': ''}):
            self.assertEqual(self.c.post('/v2/jobs', json={**payload, **changes}).status_code, 422)
        job = self.c.post('/v2/jobs', json=payload).json()
        for changes in ({'priority': None}, {'description': None}, {'job_type': 'calibration'}, {'vertical_key': 'calibration'}, {'asset_id': payload['asset_id']}, {'problem': 'legacy spelling'}):
            response = self.c.patch('/v2/jobs/' + job['id'], json={'version': job['version'], **changes})
            self.assertEqual(response.status_code, 422, response.text)

    def test_active_correction_reason_and_closed_job_guards(self):
        job = self.c.post('/v2/jobs', json=self.job_payload(draft=False)).json()
        path = '/v2/jobs/' + job['id']
        self.assertEqual(self.c.patch(path, json={'version': job['version'], 'description': 'Changed'}).status_code, 422)
        edited = self.c.patch(path, json={'version': job['version'], 'description': 'Changed', 'reason': 'Correct intake typo'})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()['intake_snapshot'], job['intake_snapshot'])
        with db() as s:
            record = s.scalar(select(Job).where(Job.public_id == job['id']))
            record.status = 'cancelled'
        response = self.c.patch(path, json={'version': edited.json()['version'], 'priority': 'low'})
        self.assertEqual(response.status_code, 409)

    def test_generic_write_permissions_scope_and_billing(self):
        from unittest.mock import patch
        from datetime import timedelta
        from app.repair_models import Workshop
        from app.repair_access import utc
        payload = self.job_payload()
        job = self.c.post('/v2/jobs', json=payload).json()
        employee, uid, rid = self.member()
        with db() as s:
            s.get(WorkshopRole, rid).permissions = ['jobs.read']
        self.assertEqual(employee.post('/v2/jobs', json=payload).status_code, 403)
        self.assertEqual(employee.patch('/v2/jobs/' + job['id'], json={'version': job['version'], 'priority': 'low'}).status_code, 403)
        with db() as s:
            s.get(WorkshopRole, rid).permissions = ['jobs.read', 'jobs.edit', 'jobs.create', 'customers.read']
            s.scalar(select(Job).where(Job.public_id == job['id'])).assigned_to = self.c.get('/me').json()['id']
        self.assertEqual(employee.patch('/v2/jobs/' + job['id'], json={'version': job['version'], 'priority': 'low'}).status_code, 404)
        allowed = employee.post('/v2/jobs', json=payload)
        self.assertEqual(allowed.status_code, 201, allowed.text)
        with db() as s:
            s.get(Workshop, self.shop['id']).trial_until = utc() - timedelta(days=10)
        with patch.dict('os.environ', {'BILLING_ENFORCED': 'true'}):
            self.assertEqual(self.c.post('/v2/jobs', json=payload).status_code, 402)
            self.assertEqual(self.c.patch('/v2/jobs/' + job['id'], json={'version': job['version'], 'priority': 'low'}).status_code, 402)

    def test_job_metadata_is_frozen_and_warranty_inherits_it(self):
        from app.repair_models import Workshop, Device
        payload = self.job_payload()
        site = self.c.post('/v2/sites', json={'customer_id': payload['customer_id'], 'name': 'Original site'}).json()
        job = self.c.post('/v2/jobs', json={**payload, 'site_id': site['id']}).json()
        with db() as s:
            s.get(Workshop, self.shop['id']).vertical_key = 'jewellery'
            s.get(Device, payload['asset_id']).site_id = None
            s.scalar(select(Job).where(Job.public_id == job['id'])).status = 'issued'
        persisted = self.c.get('/v2/jobs/' + job['id']).json()
        self.assertEqual((persisted['vertical_key'], persisted['site_id']), ('repair', site['id']))
        new = self.c.post('/v2/jobs', json=payload).json()
        self.assertEqual(new['vertical_key'], 'jewellery')
        warranty = self.c.post('/v2/orders/' + job['id'] + '/warranty', json={'version': job['version'], 'text': 'Warranty inspection'})
        self.assertEqual(warranty.status_code, 201, warranty.text)
        inherited = self.c.get('/v2/jobs/' + warranty.json()['id']).json()
        for key in ('vertical_key', 'job_type', 'priority', 'site_id'):
            self.assertEqual(inherited[key], job[key])
