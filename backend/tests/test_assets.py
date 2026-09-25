import unittest
import test_workshop as fixtures
from sqlalchemy import select
from app.database import db
from app.repair_models import WorkshopRole, RepairOrder


class AssetTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    member = fixtures.WorkshopTest.member

    def create_customer(self, client=None):
        response = (client or self.c).post(
            "/v2/customer-records",
            json={
                "name": "Laboratory",
                "kind": "company",
                "company_name": "Precision Lab",
                "tax_id": "PL123",
                "address": "Main street",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_asset(self, customer=None, **extra):
        customer = customer or self.create_customer()
        payload = {
            "customer_id": customer["id"],
            "name": "Gauge A",
            "asset_type": "instrument",
            "serial": "SN-42",
            **extra,
        }
        r = self.c.post("/v2/assets", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json(), payload

    def test_existing_devices_are_assets_and_history_preserves_order(self):
        job = self.order()
        asset = self.c.get("/v2/assets/" + str(job["device_id"])).json()
        self.assertEqual(asset["name"], "ThinkPad")
        self.assertEqual(asset["customer_id"], job["customer_id"])
        self.assertEqual(
            self.c.get(f"/v2/assets/{asset['id']}/jobs").json()["items"][0]["id"],
            job["id"],
        )
        label = self.c.get(f"/v2/assets/{asset['id']}/label")
        self.assertEqual(label.status_code, 200)
        self.assertIn("<svg", label.text)
        self.assertNotIn("customer@example.com", label.text)
        self.assertNotIn("Customer", label.text)

    def test_cross_tenant_reads_mutations_and_relation_injection(self):
        customer = self.create_customer()
        site = self.c.post(
            "/v2/sites", json={"customer_id": customer["id"], "name": "Laboratory A"}
        ).json()
        asset, payload = self.create_asset(customer, site_id=site["id"])
        other, org = self.register("other-assets@example.com")
        for path in (
            f"/assets/{asset['id']}",
            f"/assets/{asset['id']}/jobs",
            f"/assets/{asset['id']}/files",
            f"/assets/{asset['id']}/label",
            f"/customer-records/{customer['id']}",
            f"/sites/{site['id']}",
        ):
            self.assertEqual(other.get("/v2" + path).status_code, 404, path)
        self.assertEqual(
            other.patch(
                "/v2/assets/" + str(asset["id"]),
                json={**payload, "version": asset["version"]},
            ).status_code,
            404,
        )
        self.assertEqual(other.post("/v2/assets", json=payload).status_code, 404)
        self.assertEqual(
            other.post(
                "/v2/sites", json={"customer_id": customer["id"], "name": "Injected"}
            ).status_code,
            404,
        )
        self.assertEqual(
            other.patch(
                "/v2/sites/" + str(site["id"]),
                json={"customer_id": customer["id"], "name": "Injected", "version": 1},
            ).status_code,
            404,
        )
        local = self.create_customer(other)
        self.assertEqual(
            other.post(
                "/v2/assets", json={**payload, "customer_id": local["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(other.get("/v2/assets").json()["items"], [])

    def test_asset_versions_unique_external_id_and_customer_ownership(self):
        asset, payload = self.create_asset(external_id="EXT-42")
        response = self.c.patch(
            "/v2/assets/" + str(asset["id"]),
            json={**payload, "name": "Gauge revised", "version": asset["version"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.c.patch(
                "/v2/assets/" + str(asset["id"]),
                json={**payload, "version": asset["version"]},
            ).status_code,
            409,
        )
        self.assertEqual(self.c.post("/v2/assets", json=payload).status_code, 409)
        second = self.create_customer()
        self.assertEqual(
            self.c.patch(
                "/v2/assets/" + str(asset["id"]),
                json={
                    **payload,
                    "customer_id": second["id"],
                    "version": response.json()["version"],
                },
            ).status_code,
            422,
        )
        site = self.c.post(
            "/v2/sites", json={"customer_id": second["id"], "name": "Other site"}
        ).json()
        self.assertEqual(
            self.c.post(
                "/v2/assets",
                json={**payload, "external_id": "NEW", "site_id": site["id"]},
            ).status_code,
            422,
        )

    def test_cursor_search_and_own_scope(self):
        jobs = [self.order(serial="UNIQUE-" + str(i)) for i in range(3)]
        first = self.c.get("/v2/assets?limit=2").json()
        second = self.c.get("/v2/assets?limit=2&after=" + str(first["next"])).json()
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(len(second["items"]), 1)
        self.assertEqual(
            self.c.get("/v2/assets?q=UNIQUE-1").json()["items"][0]["id"],
            jobs[1]["device_id"],
        )
        worker, user_id, role_id = self.member()
        with db() as s:
            role = s.get(WorkshopRole, role_id)
            role.permissions = ["jobs.read", "assets.read", "assets.write"]
            hidden = s.scalar(
                select(RepairOrder).where(RepairOrder.public_id == jobs[0]["id"])
            )
            hidden.assigned_to = self.c.get("/me").json()["id"]
        self.assertEqual(
            worker.get("/v2/assets/" + str(jobs[0]["device_id"])).status_code, 404
        )
        self.assertEqual(len(worker.get("/v2/assets").json()["items"]), 2)
        self.assertEqual(
            worker.post(
                "/v2/assets",
                json={"customer_id": jobs[1]["customer_id"], "name": "Forbidden"},
            ).status_code,
            403,
        )
