import unittest
import test_workshop as fixtures
from sqlalchemy import select
from app.database import db
from app.repair_models import WorkshopRole


class JobTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    member = fixtures.WorkshopTest.member

    def payload(self, asset_id, **extra):
        return {
            "asset_id": asset_id,
            "template_id": self.t["id"],
            "workflow_id": self.w["id"],
            "description": "Annual inspection",
            "job_type": "inspection",
            "priority": "high",
            **extra,
        }

    def test_generic_creation_reuses_asset_and_bidirectional_compatibility(self):
        old = self.order()
        payload = self.payload(old["device_id"])
        response = self.c.post("/v2/jobs", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        job = response.json()
        self.assertEqual(job["asset_id"], old["device_id"])
        self.assertEqual(job["job_type"], "inspection")
        self.assertEqual(job["vertical_key"], "repair")
        self.assertEqual(
            self.c.get("/v2/orders/" + job["id"]).json(),
            self.c.get("/v2/jobs/" + job["id"]).json(),
        )
        changed = self.c.patch(
            "/v2/jobs/" + job["id"],
            json={
                "version": job["version"],
                "description": "Revised inspection",
                "priority": "urgent",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["description"], changed.json()["problem"])
        self.assertEqual(changed.json()["description"], "Revised inspection")
        self.assertEqual(
            self.c.patch(
                "/v2/orders/" + job["id"],
                json={"version": job["version"], "problem": "Stale"},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.c.get("/v2/jobs?job_type=inspection&priority=urgent").json()["total"],
            1,
        )
        self.assertEqual(
            self.c.get("/v2/jobs/" + old["id"]).json()["job_type"], "repair"
        )

    def test_generic_routes_cannot_bypass_tenancy_or_permission_guards(self):
        old = self.order()
        other, org = self.register("other-jobs@example.com")
        self.assertEqual(
            other.post("/v2/jobs", json=self.payload(old["device_id"])).status_code, 404
        )
        self.assertEqual(other.get("/v2/jobs/" + old["id"]).status_code, 404)
        self.assertEqual(
            other.patch(
                "/v2/jobs/" + old["id"],
                json={"version": old["version"], "description": "Injected"},
            ).status_code,
            404,
        )
        for suffix in ("events", "attachments", "history", "label", "document"):
            self.assertEqual(
                other.get("/v2/jobs/" + old["id"] + "/" + suffix).status_code, 404
            )
        employee, _, role_id = self.member()
        with db() as s:
            s.get(WorkshopRole, role_id).permissions = ["jobs.read"]
        self.assertEqual(employee.get("/v2/jobs/" + old["id"]).status_code, 200)
        self.assertEqual(
            employee.patch(
                "/v2/jobs/" + old["id"],
                json={"version": old["version"], "description": "Forbidden"},
            ).status_code,
            403,
        )
        self.assertEqual(
            employee.post(
                "/v2/jobs/" + old["id"] + "/accept", json={"version": old["version"]}
            ).status_code,
            403,
        )

    def test_generic_finance_uses_same_versions_and_payments(self):
        old = self.order()
        job = self.c.post(
            "/v2/jobs", json=self.payload(old["device_id"], draft=False)
        ).json()
        quote = self.c.post(
            "/v2/jobs/" + job["id"] + "/estimates",
            json={
                "version": job["version"],
                "lines": [
                    {"description": "Inspection", "quantity": 1, "unit_cents": 15000}
                ],
            },
        )
        self.assertEqual(quote.status_code, 201, quote.text)
        job = quote.json()["order"]
        payment = self.c.post(
            "/v2/jobs/" + job["id"] + "/payments",
            json={"version": job["version"], "amount_cents": 15000, "method": "cash"},
        )
        self.assertEqual(payment.status_code, 201, payment.text)
        self.assertEqual(
            self.c.get("/v2/orders/" + job["id"]).json()["paid_cents"], 15000
        )
        self.assertEqual(
            self.c.post(
                "/v2/jobs/" + job["id"] + "/payments",
                json={
                    "version": job["version"],
                    "amount_cents": 15000,
                    "method": "cash",
                },
            ).status_code,
            409,
        )
