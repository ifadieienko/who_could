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
        original = self.order()
        response = self.c.get('/v2/jobs/' + original['id'])
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()
        expected = dict(original)
        expected['organization_id'] = self.shop['id']
        expected['asset_id'] = expected.pop('device_id')
        expected['description'] = expected.pop('problem')
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
