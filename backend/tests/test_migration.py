"""Run the old-schema fixture in a subprocess so test databases cannot mix."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r"""
import base64,io
from datetime import datetime
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData,select
from PIL import Image
from app.database import engine,db
config=Config('alembic.ini')
command.upgrade(config,'0008_master_service_board')
m=MetaData();m.reflect(engine);now=datetime.utcnow()
image=io.BytesIO();Image.new('RGB',(5,5),'blue').save(image,'PNG')
data='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
fields=[{'id':1,'name':'Photo','field_type':'image','position':0},{'id':2,'name':'Serial','field_type':'string','position':1}]
with engine.begin() as c:
 c.execute(m.tables['roles'].delete())
 def add(table,**values):c.execute(m.tables[table].insert().values(**values))
 add('users',id=1,name='Owner',email='legacy@example.com',password_hash='legacy-hash',created_at=now)
 add('users',id=2,name='Master',email='master@example.com',password_hash='legacy-hash',created_at=now)
 add('roles',id=1,name='admin',is_system=True,created_at=now)
 add('roles',id=2,name='master',is_system=True,created_at=now)
 add('user_roles',user_id=1,role_id=1);add('user_roles',user_id=2,role_id=2)
 add('device_intake_forms',id=1,owner_id=1,name='Old form',created_at=now)
 for f in fields:add('device_intake_fields',form_id=1,**f)
 for id in (1,2,3):
  add('device_intake_orders',id=id,owner_id=1,form_id=1,form_name='Old form',fields_snapshot=fields,payload={'1':data if id!=3 else 'data:image/png;base64,invalid','2':'SN-'+str(id)},status='deferred' if id==2 else 'accepted',created_at=now,updated_at=now)
 add('master_board_columns',id=1,owner_id=2,name='Done',position=0,is_terminal=True,created_at=now)
 add('master_work_items',id=1,order_id=1,master_id=2,column_id=1,claimed_at=now,updated_at=now)
 add('customer_pickups',id=1,order_id=1,intake_owner_id=1,master_id=2,status='issued',ready_at=now,issued_at=now)
 add('warehouse_tables',id=1,owner_id=1,name='Parts',created_at=now)
command.upgrade(config,'head')
from app.legacy_photos import migrate
from app.repair_models import RepairOrder,Attachment,Membership,WorkshopRole,RepairEvent
from app.models import User,WarehouseTable,DeviceIntakeOrder
from app.repair_files import storage
migrate();migrate()
with db() as s:
 orders=s.scalars(select(RepairOrder).order_by(RepairOrder.id)).all()
 assert [o.status for o in orders]==['issued','draft','active']
 assert orders[0].assigned_to==2 and orders[0].workflow_snapshot[0]['name']=='Done'
 assert orders[0].receipt['receiver']=='Не записан в прежней версии'
 assert orders[0].values['legacy_2']=='SN-1'
 assert isinstance(orders[0].values['legacy_1'],int)
 assert orders[0].intake_snapshot['values']==orders[0].values
 assert len(s.scalars(select(Attachment)).all())==2
 assert len(list(storage().glob('*.jpg')))==4
 assert s.scalar(select(User).where(User.id==1)).password_hash=='legacy-hash'
 assert s.scalar(select(DeviceIntakeOrder).where(DeviceIntakeOrder.id==1)).payload['1']==data
 assert s.scalar(select(WarehouseTable)).workshop_id==orders[0].workshop_id
 assert len(s.scalars(select(RepairEvent).where(RepairEvent.kind=='legacy.photo_failed')).all())==1
 assert s.get(WorkshopRole,s.scalar(select(Membership).where(Membership.user_id==1)).role_id).is_owner
 assert not s.get(WorkshopRole,s.scalar(select(Membership).where(Membership.user_id==2)).role_id).is_owner
command.check(config)
"""


class LegacyMigrationTest(unittest.TestCase):
    def test_populated_v8_migration_and_photo_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                **os.environ,
                "WHO_COULD_ENV": "test",
                "WHO_COULD_SECRET": "migration-tests-only-secret-at-least-32",
                "DATABASE_URL": os.environ.get(
                    "MIGRATION_TEST_DATABASE_URL",
                    "sqlite:///" + directory + "/legacy.db",
                ),
                "UPLOAD_DIR": directory + "/uploads",
            }
            result = subprocess.run(
                [sys.executable, "-c", FIXTURE],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
