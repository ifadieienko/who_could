import unittest
import test_workshop as fixtures
from sqlalchemy import select
from app.database import db
from app.repair_models import WorkshopRole, RepairEvent
from app.core.permissions import effective_permissions


class OrganizationTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    post = fixtures.WorkshopTest.post
    quote = fixtures.WorkshopTest.quote
    member = fixtures.WorkshopTest.member

    def settings(self, **updates):
        value = self.c.get('/v2/organization').json()
        return {k: v for k, v in {**value, **updates}.items() if k not in {'id', 'vertical_key'}}

    def test_organization_alias_headers_permissions_and_isolation(self):
        self.assertEqual(self.c.get('/v2/organizations').json(), self.c.get('/v2/workshops').json())
        self.c.headers['X-Organization-Id'] = str(self.shop['id'])
        self.assertEqual(self.c.get('/v2/organization').status_code, 200)
        other, org = self.register('other@example.com')
        self.c.headers['X-Organization-Id'] = str(org['id'])
        self.assertEqual(self.c.get('/v2/organization').status_code, 400)
        del self.c.headers['X-Workshop-Id']
        self.assertEqual(self.c.get('/v2/organization').status_code, 403)
        self.c.headers['X-Organization-Id'] = str(self.shop['id'])
        self.assertEqual(self.c.get('/v2/organization').status_code, 200)
        member, _, _ = self.member()
        self.assertEqual(member.patch('/v2/organization', json=self.settings()).status_code, 403)

    def test_settings_validate_and_reject_stale_writes(self):
        original = self.settings()
        for updates in ({'timezone': 'Invalid/Zone'}, {'currency': 'BTC'}, {'locale': 'xx'}, {'country': 'POL'}):
            self.assertEqual(self.c.patch('/v2/organization', json={**original, **updates}).status_code, 422)
        updated = self.c.patch('/v2/organization', json={**original, 'timezone': 'Europe/London', 'currency': 'GBP', 'locale': 'pl'})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['version'], original['version'] + 1)
        self.assertEqual(self.c.patch('/v2/organization', json=original).status_code, 409)
        with db() as s:
            audit = s.scalar(select(RepairEvent).where(RepairEvent.kind == 'organization.updated'))
            self.assertEqual(audit.data['before']['currency'], 'PLN')
            self.assertEqual(audit.data['after']['currency'], 'GBP')

    def test_job_currency_is_frozen_and_estimates_follow_job(self):
        old = self.order(draft=False)
        self.assertEqual(old['currency'], 'PLN')
        self.assertEqual(self.c.patch('/v2/organization', json=self.settings(currency='EUR')).status_code, 200)
        new = self.order(draft=False)
        self.assertEqual(new['currency'], 'EUR')
        for order, currency in ((old, 'PLN'), (new, 'EUR')):
            result, token = self.quote(order)
            self.assertEqual(result['estimates'][0]['currency'], currency)
            self.assertEqual(self.c.get('/public/quotes/' + token).json()['currency'], currency)

    def test_granular_generic_permissions_do_not_expand_into_workflow_access(self):
        self.assertNotIn('workflows.manage', effective_permissions(['forms.manage']))
        self.assertNotIn('templates.manage', effective_permissions(['forms.manage']))
        c, _, role_id = self.member()
        with db() as s:
            role = s.get(WorkshopRole, role_id)
            role.permissions = ['jobs.read', 'forms.manage']
        self.assertEqual(c.get('/v2/orders').status_code, 200)
        self.assertEqual(c.post('/v2/templates', json={'name': 'Form', 'fields': []}).status_code, 201)
        self.assertEqual(c.post('/v2/workflows', json={'name': 'Process', 'stages': self.w['stages']}).status_code, 403)
