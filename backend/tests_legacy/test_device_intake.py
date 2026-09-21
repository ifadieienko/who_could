import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.security import SESSION_COOKIE_NAME


class DeviceIntakeApiTest(unittest.TestCase):
    def setUp(self):
        from app.database import clear_db
        clear_db()
        self.client = TestClient(app)
        self.client.cookies.clear()

    def register(self, name: str, email: str):
        response = self.client.post("/auth/register", json={"name": name, "email": email, "password": "password123"})
        self.assertEqual(response.status_code, 201, response.text)
        token = response.cookies.get(SESSION_COOKIE_NAME)
        self.assertTrue(token)
        self.client.cookies.clear()
        return {"Cookie": f"{SESSION_COOKIE_NAME}={token}", "Origin": "http://testserver"}

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get("/device-intake/forms").status_code, 401)
        self.assertEqual(self.client.post("/device-intake/forms", json={"name": "Test", "fields": []}).status_code, 401)

    def test_create_list_get_and_delete_form(self):
        owner = self.register("Owner", "owner@example.com")
        payload = {
            "name": "  Приём смартфона  ",
            "fields": [
                {"name": "  Серийный номер  ", "field_type": "string"},
                {"name": "Стоимость", "field_type": "number"},
                {"name": "Дата приёмки", "field_type": "date"},
                {"name": "Фото устройства", "field_type": "image"},
                {"name": "Комментарий клиента", "field_type": "string"},
            ],
        }
        response = self.client.post("/device-intake/forms", headers=owner, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        form = response.json()
        self.assertEqual(form["name"], "Приём смартфона")
        self.assertEqual(
            [field["name"] for field in form["fields"]],
            ["Серийный номер", "Стоимость", "Дата приёмки", "Фото устройства", "Комментарий клиента"],
        )
        self.assertEqual(
            [field["field_type"] for field in form["fields"]],
            ["string", "number", "date", "image", "string"],
        )
        self.assertEqual([field["position"] for field in form["fields"]], [0, 1, 2, 3, 4])

        listed = self.client.get("/device-intake/forms", headers=owner)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()], [form["id"]])
        fetched = self.client.get(f"/device-intake/forms/{form['id']}", headers=owner)
        self.assertEqual(fetched.status_code, 200)
        fetched_form = fetched.json()
        self.assertEqual(fetched_form["id"], form["id"])
        self.assertEqual(fetched_form["name"], form["name"])
        self.assertEqual(fetched_form["fields"], form["fields"])
        self.assertTrue(fetched_form["created_at"])

        deleted = self.client.delete(f"/device-intake/forms/{form['id']}", headers=owner)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/device-intake/forms", headers=owner).json(), [])

    def test_forms_are_private_to_owner(self):
        first = self.register("First", "first@example.com")
        second = self.register("Second", "second@example.com")
        created = self.client.post("/device-intake/forms", headers=first, json={"name": "Private", "fields": []}).json()
        self.assertEqual(self.client.get("/device-intake/forms", headers=second).json(), [])
        self.assertEqual(self.client.get(f"/device-intake/forms/{created['id']}", headers=second).status_code, 404)
        self.assertEqual(self.client.delete(f"/device-intake/forms/{created['id']}", headers=second).status_code, 404)
        self.assertEqual(self.client.get(f"/device-intake/forms/{created['id']}", headers=first).status_code, 200)

    def test_arbitrary_field_count_and_validation(self):
        owner = self.register("Owner", "owner@example.com")
        supported = ["string", "number", "date", "image"]
        fields = [
            {"name": f"Поле {index}", "field_type": supported[index % len(supported)]}
            for index in range(150)
        ]
        response = self.client.post("/device-intake/forms", headers=owner, json={"name": "Большая форма", "fields": fields})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(response.json()["fields"]), 150)
        invalid_type = self.client.post("/device-intake/forms", headers=owner, json={"name": "Bad", "fields": [{"name": "X", "field_type": "qrcode"}]})
        self.assertEqual(invalid_type.status_code, 422)
        blank_name = self.client.post("/device-intake/forms", headers=owner, json={"name": "Bad", "fields": [{"name": "   ", "field_type": "string"}]})
        self.assertEqual(blank_name.status_code, 422)


if __name__ == "__main__":
    unittest.main()
