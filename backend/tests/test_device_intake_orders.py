import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.security import SESSION_COOKIE_NAME


IMAGE = "data:image/png;base64,iVBORw0KGgo="


class DeviceIntakeOrderApiTest(unittest.TestCase):
    def setUp(self):
        from app.database import clear_db
        clear_db()
        self.client = TestClient(app)
        self.client.cookies.clear()

    def register(self, name: str, email: str):
        response = self.client.post(
            "/auth/register",
            json={"name": name, "email": email, "password": "password123"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        token = response.cookies.get(SESSION_COOKIE_NAME)
        self.assertTrue(token)
        self.client.cookies.clear()
        return {"Cookie": f"{SESSION_COOKIE_NAME}={token}", "Origin": "http://testserver"}

    def create_form(self, headers):
        response = self.client.post(
            "/device-intake/forms",
            headers=headers,
            json={
                "name": "Приём ноутбука",
                "fields": [
                    {"name": "Серийный номер", "field_type": "string"},
                    {"name": "Стоимость", "field_type": "number"},
                    {"name": "Дата приёмки", "field_type": "date"},
                    {"name": "Фото устройства", "field_type": "image"},
                ],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def values_for(self, form):
        fields = {field["name"]: field for field in form["fields"]}
        return {
            str(fields["Серийный номер"]["id"]): "SN-001",
            str(fields["Стоимость"]["id"]): 1250.5,
            str(fields["Дата приёмки"]["id"]): "2026-09-06",
            str(fields["Фото устройства"]["id"]): IMAGE,
        }

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get("/device-intake/orders").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/device-intake/orders",
                json={"form_id": 1, "values": {}, "status": "deferred"},
            ).status_code,
            401,
        )

    def test_deferred_order_can_be_incomplete_then_accepted(self):
        owner = self.register("Owner", "owner@example.com")
        form = self.create_form(owner)
        serial_id = str(form["fields"][0]["id"])

        rejected = self.client.post(
            "/device-intake/orders",
            headers=owner,
            json={"form_id": form["id"], "values": {serial_id: "SN-001"}, "status": "accepted"},
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertIn("Не заполнены поля", rejected.json()["detail"])

        deferred = self.client.post(
            "/device-intake/orders",
            headers=owner,
            json={"form_id": form["id"], "values": {serial_id: "SN-001"}, "status": "deferred"},
        )
        self.assertEqual(deferred.status_code, 201, deferred.text)
        order = deferred.json()
        self.assertEqual(order["status"], "deferred")
        self.assertEqual(order["form_name"], "Приём ноутбука")
        self.assertEqual(order["values"][serial_id], "SN-001")
        self.assertEqual(len(order["fields"]), 4)

        accepted = self.client.put(
            f"/device-intake/orders/{order['id']}",
            headers=owner,
            json={"values": self.values_for(form), "status": "accepted"},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        accepted_order = accepted.json()
        self.assertEqual(accepted_order["status"], "accepted")
        self.assertEqual(accepted_order["values"], self.values_for(form))
        self.assertTrue(accepted_order["created_at"])
        self.assertTrue(accepted_order["updated_at"])

        immutable = self.client.put(
            f"/device-intake/orders/{order['id']}",
            headers=owner,
            json={"values": self.values_for(form), "status": "deferred"},
        )
        self.assertEqual(immutable.status_code, 409)

    def test_accepted_order_persists_all_types_and_is_listed(self):
        owner = self.register("Owner", "owner@example.com")
        form = self.create_form(owner)
        values = self.values_for(form)
        response = self.client.post(
            "/device-intake/orders",
            headers=owner,
            json={"form_id": form["id"], "values": values, "status": "accepted"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        order = response.json()
        self.assertEqual(order["values"], values)
        self.assertEqual([field["field_type"] for field in order["fields"]], ["string", "number", "date", "image"])

        listed = self.client.get("/device-intake/orders", headers=owner)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()], [order["id"]])
        fetched = self.client.get(f"/device-intake/orders/{order['id']}", headers=owner)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["values"], values)

    def test_order_snapshot_survives_template_deletion(self):
        owner = self.register("Owner", "owner@example.com")
        form = self.create_form(owner)
        created = self.client.post(
            "/device-intake/orders",
            headers=owner,
            json={"form_id": form["id"], "values": {}, "status": "deferred"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        order = created.json()

        deleted = self.client.delete(f"/device-intake/forms/{form['id']}", headers=owner)
        self.assertEqual(deleted.status_code, 204, deleted.text)
        fetched = self.client.get(f"/device-intake/orders/{order['id']}", headers=owner)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        snapshot = fetched.json()
        self.assertEqual(snapshot["form_name"], "Приём ноутбука")
        self.assertEqual([field["name"] for field in snapshot["fields"]], [
            "Серийный номер", "Стоимость", "Дата приёмки", "Фото устройства"
        ])

    def test_orders_are_private_to_owner(self):
        first = self.register("First", "first@example.com")
        second = self.register("Second", "second@example.com")
        form = self.create_form(first)
        order = self.client.post(
            "/device-intake/orders",
            headers=first,
            json={"form_id": form["id"], "values": {}, "status": "deferred"},
        ).json()
        self.assertEqual(self.client.get("/device-intake/orders", headers=second).json(), [])
        self.assertEqual(self.client.get(f"/device-intake/orders/{order['id']}", headers=second).status_code, 404)
        self.assertEqual(
            self.client.put(
                f"/device-intake/orders/{order['id']}",
                headers=second,
                json={"values": {}, "status": "deferred"},
            ).status_code,
            404,
        )

    def test_order_value_validation(self):
        owner = self.register("Owner", "owner@example.com")
        form = self.create_form(owner)
        fields = {field["field_type"]: field for field in form["fields"]}

        cases = [
            ({str(fields["number"]["id"]): "not-a-number"}, 422),
            ({str(fields["date"]["id"]): "2026-99-99"}, 422),
            ({str(fields["image"]["id"]): "not-an-image"}, 422),
            ({"999999": "unknown"}, 422),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                response = self.client.post(
                    "/device-intake/orders",
                    headers=owner,
                    json={"form_id": form["id"], "values": values, "status": "deferred"},
                )
                self.assertEqual(response.status_code, expected, response.text)


if __name__ == "__main__":
    unittest.main()
