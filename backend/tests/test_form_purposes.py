import io
import unittest
from PIL import Image
import test_workshop as fixtures


class FormPurposeTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.WorkshopTest.setUpClass.__func__)
    setUp = fixtures.WorkshopTest.setUp
    register = fixtures.WorkshopTest.register
    order = fixtures.WorkshopTest.order
    post = fixtures.WorkshopTest.post
    member = fixtures.WorkshopTest.member

    def template(self, purpose="measurement"):
        payload = {"name": "Measurement sheet", "purpose": purpose, "fields": [
            {"key": "reading", "label": "Reading", "type": "number", "required": True}
        ]}
        r = self.c.post("/v2/templates", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        tid = r.json()["id"]
        self.assertEqual(self.c.post(f"/v2/templates/{tid}/publish").status_code, 200)
        return tid, payload

    def test_custom_purpose_snapshots_guards_and_isolation(self):
        tid, payload = self.template()
        r = self.c.post("/v2/workflows", json={"name": "Measurement", "stages": [
            {"key": "measure", "name": "Measure", "form_phase": "measurement", "next": ["ready"]},
            {"key": "ready", "name": "Ready", "category": "ready"}
        ]})
        self.assertEqual(r.status_code, 201, r.text)
        flow = r.json()["id"]
        o = self.order(workflow_id=flow, stage_forms={"measurement": tid}, draft=False)
        path = "/v2/orders/" + o["id"]
        missing = self.c.post(path + "/transition", json={"version": o["version"], "target": "ready"})
        self.assertEqual(missing.status_code, 422)
        other, _ = self.register("other-purpose@example.com")
        self.assertEqual(other.patch(path + "/forms/measurement", json={"version": o["version"], "values": {"reading": 1}}).status_code, 404)
        employee, _, _ = self.member()
        self.assertEqual(employee.post("/v2/templates", json=payload).status_code, 403)
        result = self.c.patch(path + "/forms/measurement", json={"version": o["version"], "values": {"reading": 1.25}})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.c.patch(path + "/forms/measurement", json={"version": o["version"], "values": {"reading": 2}}).status_code, 409)
        o = result.json()
        clone = self.c.post(f"/v2/templates/{tid}/version").json()["id"]
        self.assertEqual(self.c.put(f"/v2/templates/{clone}", json={**payload, "fields": []}).status_code, 200)
        self.assertEqual(self.c.post(f"/v2/templates/{clone}/publish").status_code, 200)
        o = self.post(o, "/transition", target="ready")
        o = self.post(o, "/issue", receiver="Customer")
        saved = o["receipt"]["stage_forms"]["measurement"]
        self.assertEqual(saved["values"]["reading"], 1.25)
        self.assertEqual(saved["template"]["revision"], 1)
        self.assertEqual(len(saved["template"]["fields"]), 1)

    def test_purpose_validation_matching_and_photos(self):
        tid, payload = self.template("jewellery_condition")
        for purpose in ["", "bad/key", "Uppercase", "x" * 21]:
            self.assertEqual(self.c.post("/v2/templates", json={**payload, "purpose": purpose}).status_code, 422)
        o = self.order(stage_forms={"jewellery_condition": tid})
        base = {"template_id": self.t["id"], "workflow_id": self.w["id"], "customer_id": o["customer_id"], "asset_id": o["device_id"], "description": "Inspect"}
        for slot in ["intake", "measurement", "bad/key"]:
            self.assertEqual(self.c.post("/v2/jobs", json={**base, "stage_forms": {slot: tid}}).status_code, 422)
        other, _ = self.register("foreign-template@example.com")
        foreign = other.get("/v2/templates").json()[0]["id"]
        self.assertEqual(self.c.post("/v2/jobs", json={**base, "stage_forms": {"measurement": foreign}}).status_code, 404)
        result = self.c.post("/v2/jobs", json={**base, "stage_forms": {"jewellery_condition": tid}})
        self.assertEqual(result.status_code, 201, result.text)
        img = io.BytesIO()
        Image.new("RGB", (2, 2)).save(img, format="PNG")
        path = "/v2/orders/" + o["id"] + "/attachments"
        for phase, status in [("not_assigned", 422), ("jewellery_condition", 201)]:
            r = self.c.post(path, data={"version": o["version"], "phase": phase}, files={"file": ("test.png", img.getvalue(), "image/png")})
            self.assertEqual(r.status_code, status, r.text)
