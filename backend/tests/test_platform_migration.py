"""A populated 0010 database survives every subsequent platform migration."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

FIXTURE = r'''
from datetime import datetime
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, JSON, select
from app.database import engine
config = Config('alembic.ini')
command.upgrade(config, '0010_stage_forms_plans')
m = MetaData(); m.reflect(engine); now = datetime(2026, 1, 5, 12, 0)
json_columns = {
 'workshop_roles': ['permissions'], 'repair_templates': ['fields', 'layout'],
 'repair_workflows': ['stages'], 'repair_orders': ['template_snapshot','intake_snapshot','values','stage_forms','workflow_snapshot','checks','receipt'],
 'repair_events': ['data'], 'repair_estimates': ['lines'],
}
for table, cols in json_columns.items():
 for col in cols: m.tables[table].c[col].type = JSON()
fields = [{'key':'note','label':'Finding','type':'text'}]
stages = [{'key':'received','name':'Received','category':'active','next':['ready']}, {'key':'ready','name':'Ready','category':'ready','next':[]}]
form = {'id':1,'name':'Original','revision':1,'purpose':'intake','fields':fields,'layout':{'columns':2}}
stage_forms = {'diagnosis': {'template':{**form,'purpose':'diagnosis'},'values':{'note':'Historical finding'}}}
with engine.begin() as c:
 def add(table, **values): c.execute(m.tables[table].insert().values(**values))
 add('users',id=1,name='Owner',email='v10@example.com',password_hash='preserved-hash',created_at=now)
 add('workshops',id=1,name='Existing',created_at=now,trial_until=now,billing_status='trialing',plan='starter',billing_updated=0)
 add('workshop_roles',id=1,workshop_id=1,name='owner',permissions=['orders.read','orders.create','templates.manage','contacts.read'],scope='all',is_owner=True)
 add('workshop_members',id=1,workshop_id=1,user_id=1,role_id=1,active=True)
 add('repair_customers',id=1,workshop_id=1,name='Existing client',email='customer@example.com',phone='+48123456789')
 add('repair_devices',id=1,workshop_id=1,customer_id=1,model='Original device',serial='SN-v10')
 add('repair_templates',id=1,workshop_id=1,family='original-form',name='Original',revision=1,published=True,archived=False,purpose='intake',fields=fields,layout={'columns':2})
 add('repair_workflows',id=1,workshop_id=1,family='original-process',name='Original',revision=1,stages=stages,archived=False)
 add('repair_orders',id=1,public_id='preserve-this-link',workshop_id=1,created_by=1,assigned_to=1,customer_id=1,device_id=1,problem='Old fault',condition='Scratched',accessories='Case',location='Shelf 2',template_snapshot=form,intake_snapshot={'values':{'note':'At intake'}},values={'note':'Latest'},stage_forms=stage_forms,workflow_snapshot=stages,stage='received',status='active',checks={},version=7,created_at=now,updated_at=now,stage_entered_at=now)
 add('repair_events',id=1,workshop_id=1,order_id=1,actor_id=1,kind='order.created',data={'source':'fixture'},created_at=now)
 add('repair_attachments',id=1,workshop_id=1,order_id=1,storage_key='preserved-file-key',filename='photo.jpg',phase='intake',size=123,created_at=now)
 add('repair_estimates',id=1,workshop_id=1,order_id=1,revision=2,lines=[{'description':'Old quote','quantity':1,'unit_cents':12500}],total_cents=12500,currency='PLN',status='accepted',token_hash='a'*64,expires_at=now,decision_at=now,decision_name='Customer',created_at=now)
 add('repair_payments',id=1,workshop_id=1,order_id=1,amount_cents=12500,method='cash',reference='v10',created_at=now)
 before = {name: [dict(row) for row in c.execute(select(table)).mappings()] for name, table in m.tables.items() if name != 'alembic_version'}
command.upgrade(config, 'head')
# Query through the old reflected columns: every original value must survive,
# except permission lists which may gain backward-compatible aliases.
with engine.connect() as c:
 for name, old_rows in before.items():
  new_rows = [dict(row) for row in c.execute(select(m.tables[name])).mappings()]
  assert len(old_rows) == len(new_rows), name
  for old, new in zip(old_rows, new_rows):
   if name == 'workshop_roles':
    assert set(old.pop('permissions')) <= set(new.pop('permissions'))
   assert old == new, (name, old, new)
 from app.repair_models import Workshop, RepairOrder
 assert c.execute(select(Workshop.currency)).scalar_one() == 'PLN'
 assert c.execute(select(RepairOrder.currency)).scalar_one() == 'PLN'
command.check(config)
'''


class PlatformMigrationTest(unittest.TestCase):
    def test_populated_v10_to_head_preserves_original_values(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-c', FIXTURE],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, 'WHO_COULD_ENV':'test', 'WHO_COULD_SECRET':'migration-test-secret-at-least-32-characters',
                     'DATABASE_URL':os.environ.get('PLATFORM_MIGRATION_TEST_DATABASE_URL', 'sqlite:///' + directory + '/platform.db')},
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
