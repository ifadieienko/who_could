import os, tempfile, unittest, io, json, zipfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
ROOT = Path(__file__).resolve().parents[1]
os.environ.update(
    WHO_COULD_ENV="test",
    WHO_COULD_SECRET="tests-only-secret-that-is-at-least-32-characters",
    DATABASE_URL=os.environ.get(
        "TEST_DATABASE_URL", "sqlite:///" + TEMP.name + "/test.db"
    ),
    UPLOAD_DIR=TEMP.name + "/uploads",
    PUBLIC_URL="https://repair.example.com",
    BILLING_ENFORCED="false",
)
from alembic.config import Config
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select
from PIL import Image
from app.main import app
from app.database import engine, db
from app.models import Base
from app.repair_models import RepairOrder, Workshop
from app.repair_access import utc
from app.security import SESSION_COOKIE_NAME


def config():
    c = Config(str(ROOT / "alembic.ini"))
    c.set_main_option("script_location", str(ROOT / "migrations"))
    return c


class WorkshopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        command.upgrade(config(), "head")

    def setUp(self):
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
        self.c, self.shop = self.register("owner@example.com")
        self.t = self.c.get("/v2/templates").json()[0]
        self.w = self.c.get("/v2/workflows").json()[0]

    def register(self, email):
        c = TestClient(app)
        r = c.post(
            "/auth/register",
            json={
                "name": "Owner",
                "email": email,
                "password": "secure-password-123",
                "workshop": "Workshop " + email,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        w = c.get("/v2/workshops").json()[0]
        c.headers.update({"X-Workshop-Id": str(w["id"]), "Origin": "http://testserver"})
        return c, w

    def order(self, **extra):
        r = self.c.post(
            "/v2/orders",
            json={
                "template_id": self.t["id"],
                "workflow_id": self.w["id"],
                "customer": {"name": "Customer", "email": "customer@example.com"},
                "model": "ThinkPad",
                "serial": "SN001",
                "problem": "No power",
                "condition": "Scratch",
                "accessories": "Charger",
                **extra,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def post(self, o, suffix, **body):
        r = self.c.post(
            "/v2/orders/" + o["id"] + suffix, json={"version": o["version"], **body}
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def edit(self, o, **body):
        r = self.c.patch(
            "/v2/orders/" + o["id"], json={"version": o["version"], **body}
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def member(self, role="master", email="master@example.com"):
        rid = next(
            x["id"]
            for x in self.c.get("/v2/roles").json()["roles"]
            if x["name"] == role
        )
        r = self.c.post(
            "/v2/members",
            json={
                "name": "Employee",
                "email": email,
                "password": "secure-password-123",
                "role_id": rid,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        c = TestClient(app)
        self.assertEqual(
            c.post(
                "/auth/login", json={"email": email, "password": "secure-password-123"}
            ).status_code,
            200,
        )
        c.headers.update(
            {"X-Workshop-Id": str(self.shop["id"]), "Origin": "http://testserver"}
        )
        return c, r.json()["id"], rid

    def quote(self, o):
        r = self.c.post(
            "/v2/orders/" + o["id"] + "/estimates",
            json={
                "version": o["version"],
                "lines": [
                    {"description": "Repair", "quantity": 1, "unit_cents": 12000}
                ],
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["order"], r.json()["approval_path"].split("/")[-1]

    def ready(self, o):
        if o["status"] == "draft":
            o = self.post(o, "/accept")
        o = self.edit(o, values={"diagnosis": "Board failure", "work_done": "Repaired"})
        o = self.post(o, "/transition", target="diagnosis")
        o, token = self.quote(o)
        self.assertEqual(
            TestClient(app)
            .post(
                "/public/quotes/" + token,
                json={"decision": "accepted", "name": "Customer", "confirmed": True},
            )
            .status_code,
            200,
        )
        o = self.c.get("/v2/orders/" + o["id"]).json()
        o = self.post(o, "/transition", target="repair")
        o = self.post(o, "/transition", target="quality")
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/transition",
                json={"version": o["version"], "target": "ready"},
            ).status_code,
            422,
        )
        return self.post(
            o,
            "/transition",
            target="ready",
            checks=[
                "Комплектность проверена",
                "Неисправность устранена",
                "Финальный тест пройден",
            ],
        )

    def test_full_repair_payment_issue_warranty(self):
        o = self.ready(self.order())
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/issue",
                json={"version": o["version"], "receiver": "Customer"},
            ).status_code,
            422,
        )
        r = self.c.post(
            "/v2/orders/" + o["id"] + "/payments",
            json={"version": o["version"], "amount_cents": 12000, "method": "cash"},
        )
        self.assertEqual(r.status_code, 201, r.text)
        o = r.json()
        o = self.post(o, "/issue", receiver="Customer")
        self.assertEqual(o["status"], "issued")
        self.assertEqual(
            self.c.get("/v2/orders?status=issued").json()["items"][0]["status"],
            "issued",
        )
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/issue",
                json={"version": o["version"], "receiver": "Customer"},
            ).status_code,
            409,
        )
        r = self.c.post(
            "/v2/orders/" + o["id"] + "/warranty",
            json={"version": o["version"], "text": "Fault returned"},
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["warranty_of"], o["id"])
        self.assertEqual(r.json()["device_id"], o["device_id"])
        self.assertEqual(
            len(self.c.get("/v2/orders/" + o["id"] + "/history").json()), 2
        )

    def test_cross_tenant_access(self):
        o = self.order()
        c, w = self.register("other@example.com")
        self.assertEqual(c.get("/v2/orders/" + o["id"]).status_code, 404)
        self.assertEqual(c.get("/v2/orders").json()["total"], 0)
        self.assertEqual(
            c.post(
                "/v2/orders",
                json={
                    "template_id": self.t["id"],
                    "workflow_id": self.w["id"],
                    "model": "X",
                    "problem": "X",
                    "customer": {"name": "X"},
                },
            ).status_code,
            404,
        )
        c.headers["X-Workshop-Id"] = str(self.shop["id"])
        self.assertEqual(c.get("/v2/orders").status_code, 403)

    def test_deactivation_preserves_history(self):
        c, uid, rid = self.member("reception")
        r = c.post(
            "/v2/orders",
            json={
                "template_id": self.t["id"],
                "workflow_id": self.w["id"],
                "model": "Phone",
                "problem": "Broken",
                "customer": {"name": "Client"},
            },
        )
        self.assertEqual(r.status_code, 201)
        id = r.json()["id"]
        self.assertEqual(
            self.c.patch(
                "/v2/members/" + str(uid), json={"role_id": rid, "active": False}
            ).status_code,
            200,
        )
        self.assertEqual(c.get("/v2/orders/" + id).status_code, 403)
        self.assertEqual(self.c.get("/v2/orders/" + id).status_code, 200)
        self.assertEqual(self.c.delete("/admin/users/" + str(uid)).status_code, 404)

    def test_scope_and_permissions(self):
        c, uid, _ = self.member()
        other, oid, _ = self.member(email="second@example.com")
        o = self.post(self.order(), "/assign", user_id=uid)
        self.assertEqual(c.get("/v2/orders/" + o["id"]).status_code, 200)
        self.assertEqual(other.get("/v2/orders/" + o["id"]).status_code, 404)
        self.assertIsNone(c.get("/v2/orders/" + o["id"]).json()["customer"])
        self.assertEqual(
            c.post("/v2/templates", json={"name": "x", "fields": []}).status_code, 403
        )

    def test_conflict_and_snapshot(self):
        o = self.order(draft=False)
        updated = self.edit(o, location="B12")
        self.assertEqual(
            self.c.patch(
                "/v2/orders/" + o["id"],
                json={"version": o["version"], "location": "C12"},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.c.patch(
                "/v2/orders/" + o["id"],
                json={"version": updated["version"], "condition": "Changed"},
            ).status_code,
            422,
        )
        changed = self.edit(updated, condition="Changed", reason="Correction")
        self.assertEqual(changed["intake_snapshot"]["condition"], "Scratch")

    def test_transition_guards(self):
        o = self.order(draft=False)
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/transition",
                json={"version": o["version"], "target": "ready"},
            ).status_code,
            409,
        )
        o = self.post(o, "/transition", target="diagnosis")
        o = self.edit(o, values={"diagnosis": "Fault"})
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/transition",
                json={"version": o["version"], "target": "repair"},
            ).status_code,
            409,
        )

    def test_conditional_fields_and_versions(self):
        fields = [
            *self.t["fields"],
            {"key": "wet", "label": "Wet", "type": "checkbox"},
            {
                "key": "details",
                "label": "Liquid",
                "required": True,
                "condition": {"field": "wet", "equals": True},
            },
        ]
        r = self.c.post(
            "/v2/templates",
            json={"name": "Conditional", "fields": fields, "columns": 3},
        )
        self.assertEqual(r.status_code, 201, r.text)
        id = r.json()["id"]
        self.c.post(f"/v2/templates/{id}/publish")
        o = self.order(template_id=id, values={"wet": False}, draft=False)
        r = self.c.post(
            "/v2/orders",
            json={
                "template_id": id,
                "workflow_id": self.w["id"],
                "customer": {"name": "A"},
                "model": "A",
                "problem": "A",
                "values": {"wet": True},
                "draft": False,
            },
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(
            self.c.put(
                f"/v2/templates/{id}", json={"name": "Changed", "fields": fields}
            ).status_code,
            409,
        )
        v = self.c.post(f"/v2/templates/{id}/version").json()["id"]
        self.assertEqual(
            self.c.put(
                f"/v2/templates/{v}", json={"name": "Changed", "fields": fields}
            ).status_code,
            200,
        )
        self.c.post(f"/v2/templates/{id}/archive")
        self.assertEqual(
            self.c.get("/v2/orders/" + o["id"]).json()["template"]["name"],
            "Conditional",
        )

    def test_field_privacy(self):
        fields = [
            *self.t["fields"],
            {
                "key": "secret",
                "label": "Private",
                "type": "string",
                "read_permission": "finance.read",
                "write_permission": "finance.write",
            },
        ]
        id = self.c.post(
            "/v2/templates", json={"name": "Private", "fields": fields}
        ).json()["id"]
        self.c.post(f"/v2/templates/{id}/publish")
        o = self.order(template_id=id, values={"secret": "hidden-value"}, draft=False)
        c, uid, _ = self.member()
        o = self.post(o, "/assign", user_id=uid)
        self.assertNotIn("hidden-value", c.get("/v2/orders/" + o["id"]).text)
        self.assertEqual(
            c.patch(
                "/v2/orders/" + o["id"],
                json={"version": o["version"], "values": {"secret": "changed"}},
            ).status_code,
            403,
        )
        self.assertEqual(c.get("/v2/orders/" + o["id"] + "/document").status_code, 403)

    def test_photos_and_full_export(self):
        o = self.order()
        img = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(img, "PNG")
        r = self.c.post(
            "/v2/orders/" + o["id"] + "/attachments",
            data={"version": o["version"], "phase": "intake"},
            files={"file": ("photo.png", img.getvalue(), "image/png")},
        )
        self.assertEqual(r.status_code, 201, r.text)
        fid = r.json()["id"]
        self.assertEqual(self.c.get(f"/v2/files/{fid}?thumb=true").status_code, 200)
        other, _ = self.register("secondshop@example.com")
        self.assertEqual(other.get(f"/v2/files/{fid}").status_code, 404)
        o = self.c.get("/v2/orders/" + o["id"]).json()
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/attachments",
                data={"version": o["version"]},
                files={"file": ("fake.png", b"not an image", "image/png")},
            ).status_code,
            422,
        )
        r = self.c.get("/v2/export")
        self.assertEqual(r.status_code, 200, r.text[:200])
        archive = zipfile.ZipFile(io.BytesIO(r.content))
        self.assertTrue(any(x.startswith("files/") for x in archive.namelist()))
        data = json.loads(archive.read("workshop.json"))
        self.assertEqual(len(data["repair_orders"]), 1)
        self.assertNotIn("password_hash", archive.read("workshop.json").decode())

    def test_quote_version_and_replay(self):
        o, old = self.quote(self.order(draft=False))
        o, token = self.quote(o)
        c = TestClient(app)
        self.assertEqual(c.get("/public/quotes/" + old).status_code, 410)
        r = c.get("/public/quotes/" + token)
        self.assertEqual(r.json()["total_cents"], 12000)
        self.assertNotIn("Customer", r.text)
        decision = {"decision": "accepted", "name": "Client", "confirmed": True}
        self.assertEqual(
            c.post("/public/quotes/" + token, json=decision).status_code, 200
        )
        self.assertEqual(
            c.post("/public/quotes/" + token, json=decision).status_code, 409
        )

    def test_csv_preview_idempotency_atomicity(self):
        text = "external_id,customer_external_id,name,email,model,problem\n1,c1,Client,test@example.com,Phone,Broken\n2,c1,Client,test@example.com,Laptop,Broken\n"
        data = {
            "template_id": self.t["id"],
            "workflow_id": self.w["id"],
            "kind": "orders",
            "dry_run": "true",
        }

        def send():
            return self.c.post(
                "/v2/import/csv",
                data=data,
                files={"file": ("data.csv", text, "text/csv")},
            )

        r = send()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["created"], 2)
        self.assertEqual(self.c.get("/v2/orders").json()["total"], 0)
        data["dry_run"] = "false"
        self.assertEqual(send().json()["created"], 2)
        self.assertEqual(send().json()["skipped"], 2)
        self.assertEqual(len(self.c.get("/v2/customers").json()), 1)
        text += "3,c2,,invalid,Phone,Broken\n"
        self.assertFalse(send().json()["valid"])
        self.assertEqual(self.c.get("/v2/orders").json()["total"], 2)

    def test_stalled_and_pagination(self):
        o = self.order(draft=False)
        with db() as s:
            s.scalar(
                select(RepairOrder).where(RepairOrder.public_id == o["id"])
            ).stage_deadline = utc() - timedelta(hours=1)
        self.assertEqual(self.c.get("/v2/orders?stalled=true").json()["total"], 1)
        self.assertEqual(self.c.get("/v2/orders?page=2&limit=1").json()["items"], [])

    def test_logout_csrf_legacy(self):
        token = self.c.cookies.get(SESSION_COOKIE_NAME)
        self.assertEqual(self.c.post("/auth/logout").status_code, 204)
        self.c.cookies.set(SESSION_COOKIE_NAME, token)
        self.assertEqual(self.c.get("/me").status_code, 401)
        self.assertEqual(self.c.get("/jobs").status_code, 404)
        self.assertEqual(self.c.get("/admin/users").status_code, 404)

    def test_csrf(self):
        self.c.headers["Origin"] = "https://attacker.example.com"
        self.assertEqual(
            self.c.post("/v2/templates", json={"name": "x", "fields": []}).status_code,
            403,
        )

    def test_expired_subscription_can_export(self):
        o = self.order()
        with db() as s:
            s.get(Workshop, self.shop["id"]).trial_until = utc() - timedelta(days=9)
        with patch.dict(os.environ, {"BILLING_ENFORCED": "true"}):
            self.assertEqual(
                self.c.patch(
                    "/v2/orders/" + o["id"],
                    json={"version": o["version"], "location": "new"},
                ).status_code,
                402,
            )
            self.assertEqual(self.c.get("/v2/orders").status_code, 200)
            self.assertEqual(self.c.get("/v2/export").status_code, 200)

    def test_warehouse_tenant_scope(self):
        r = self.c.post(
            "/warehouse/tables",
            json={
                "name": "Parts",
                "columns": [{"name": "Part", "field_type": "string"}],
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        id = r.json()["id"]
        other, _ = self.register("other@example.com")
        self.assertEqual(other.get("/warehouse/tables/" + str(id)).status_code, 404)

    def test_webhook_signature_and_replay(self):
        import hmac, hashlib, time
        from app.billing import verify_signature

        secret = "test-webhook"
        raw = json.dumps(
            {
                "id": "evt_one",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": "sub_one"}},
            }
        ).encode()
        stamp = str(int(time.time()))
        sig = hmac.new(
            secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        header = "t=" + stamp + ",v1=" + sig
        self.assertTrue(verify_signature(raw, header, secret))
        self.assertFalse(verify_signature(raw + b"x", header, secret))
        sub = {
            "id": "sub_one",
            "customer": "cus_one",
            "status": "active",
            "current_period_end": int(time.time()) + 86400,
            "metadata": {"workshop_id": str(self.shop["id"])},
        }
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": secret}), patch(
            "app.billing.stripe", return_value=sub
        ):
            self.assertEqual(
                self.c.post(
                    "/billing/webhook",
                    content=raw,
                    headers={"stripe-signature": header},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.c.post(
                    "/billing/webhook",
                    content=raw,
                    headers={"stripe-signature": header},
                ).status_code,
                200,
            )

    def test_print_and_escape(self):
        o = self.order(problem="<script>alert(1)</script>", draft=False)
        r = self.c.get("/v2/orders/" + o["id"] + "/document")
        self.assertEqual(r.status_code, 200)
        self.assertIn("&lt;script&gt;", r.text)
        self.assertNotIn("<script>", r.text)
        self.assertIn("<svg", self.c.get("/v2/orders/" + o["id"] + "/label").text)

    def test_reopen_retains_receipt_and_field_audit(self):
        o = self.ready(self.order())
        o = self.post(
            o, "/issue", receiver="Customer", outstanding_reason="Payment later"
        )
        receipt = o["receipt"]
        o = self.post(o, "/reopen", reason="Additional work")
        entry = next(e for e in o["events"] if e["kind"] == "order.reopened")
        self.assertEqual(entry["data"]["previous_receipt"], receipt)
        o = self.edit(o, values={"diagnosis": "Updated diagnosis"})
        self.assertEqual(
            o["events"][0]["data"]["value_changes"]["diagnosis"]["before"],
            "Board failure",
        )

    def test_declined_revised_estimate_cannot_zero_issue(self):
        o = self.ready(self.order())
        o, token = self.quote(o)
        self.assertEqual(
            TestClient(app)
            .post(
                "/public/quotes/" + token,
                json={"decision": "declined", "name": "Customer", "confirmed": True},
            )
            .status_code,
            200,
        )
        o = self.c.get("/v2/orders/" + o["id"]).json()
        self.assertEqual(
            self.c.post(
                "/v2/orders/" + o["id"] + "/issue",
                json={"version": o["version"], "receiver": "Customer"},
            ).status_code,
            409,
        )

    def test_reset_revokes_sessions_and_token_is_single_use(self):
        from app.repair_models import Outbox

        with patch.dict(
            os.environ, {"SMTP_HOST": "test.invalid", "SMTP_FROM": "robot@example.com"}
        ):
            self.assertEqual(
                self.c.post(
                    "/auth/reset-request", json={"email": "owner@example.com"}
                ).status_code,
                200,
            )
        with db() as s:
            token = s.scalar(
                select(Outbox).where(Outbox.subject == "Сброс пароля")
            ).body.split("/")[-1]
        client = TestClient(app)
        body = {"token": token, "password": "a-new-secure-password"}
        self.assertEqual(
            client.post("/auth/reset-password", json=body).status_code, 200
        )
        self.assertEqual(self.c.get("/me").status_code, 401)
        self.assertEqual(
            client.post("/auth/reset-password", json=body).status_code, 410
        )
        self.assertEqual(
            client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": body["password"]},
            ).status_code,
            200,
        )

    def test_owner_and_null_validation(self):
        owner = self.c.get("/me").json()["id"]
        roles = self.c.get("/v2/roles").json()["roles"]
        rid = next(x["id"] for x in roles if x["name"] == "master")
        self.assertEqual(
            self.c.patch(
                "/v2/members/" + str(owner), json={"role_id": rid, "active": False}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.c.post(
                "/v2/roles",
                json={"name": "Escalation", "permissions": ["members.manage"]},
            ).status_code,
            422,
        )
        o = self.order()
        self.assertEqual(
            self.c.patch(
                "/v2/orders/" + o["id"], json={"version": o["version"], "problem": None}
            ).status_code,
            422,
        )
        self.assertEqual(
            TestClient(app)
            .post(
                "/auth/login",
                headers={"Origin": "https://evil.invalid"},
                json={"email": "owner@example.com", "password": "secure-password-123"},
            )
            .status_code,
            403,
        )

    def test_outbox_retry_then_success(self):
        from app.repair_models import Outbox
        from app.mail_worker import deliver_once
        import smtplib

        self.ready(self.order())
        with patch.dict(
            os.environ, {"SMTP_HOST": "test.invalid", "SMTP_FROM": "robot@example.com"}
        ), patch(
            "app.mail_worker.smtplib.SMTP", side_effect=smtplib.SMTPException("offline")
        ):
            self.assertEqual(deliver_once(), 0)
        with db() as s:
            messages = s.scalars(select(Outbox)).all()
            self.assertTrue(messages)
            self.assertTrue(all(m.attempts == 1 for m in messages))
            for m in messages:
                m.next_attempt = utc() - timedelta(seconds=1)
        with patch.dict(
            os.environ, {"SMTP_HOST": "test.invalid", "SMTP_FROM": "robot@example.com"}
        ), patch("app.mail_worker.smtplib.SMTP"):
            self.assertEqual(deliver_once(), len(messages))

    def test_schema_matches(self):
        command.check(config())


if __name__ == "__main__":
    unittest.main()
