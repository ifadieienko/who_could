import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.security import SESSION_COOKIE_NAME


class WarehouseApiTest(unittest.TestCase):
    def setUp(self):
        from app.database import clear_db
        clear_db()
        self.client = TestClient(app)
        self.client.cookies.clear()

    def register(self, name: str, email: str):
        response = self.client.post("/auth/register", json={"name": name, "email": email, "password": "password123"})
        self.assertEqual(response.status_code, 201, response.text)
        token = response.cookies.get(SESSION_COOKIE_NAME)
        self.client.cookies.clear()
        return {"Cookie": f"{SESSION_COOKIE_NAME}={token}", "Origin": "http://testserver"}

    def create_table(self, headers):
        response = self.client.post("/warehouse/tables", headers=headers, json={
            "name": "  Основной склад  ",
            "columns": [
                {"name": "Модель", "field_type": "string"},
                {"name": "Количество", "field_type": "number"},
                {"name": "Дата приёмки", "field_type": "date"},
                {"name": "Фото", "field_type": "image"},
                {"name": "Штрих-код", "field_type": "barcode"},
                {"name": "QR", "field_type": "qrcode"},
            ],
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get("/warehouse/tables").status_code, 401)
        self.assertEqual(self.client.post("/warehouse/tables", json={"name": "X", "columns": []}).status_code, 401)

    def test_create_table_and_row_with_all_types(self):
        owner = self.register("Owner", "owner@example.com")
        table = self.create_table(owner)
        self.assertEqual(table["name"], "Основной склад")
        self.assertEqual([column["position"] for column in table["columns"]], list(range(6)))
        self.assertEqual([column["field_type"] for column in table["columns"]], ["string", "number", "date", "image", "barcode", "qrcode"])

        ids = {column["name"]: str(column["id"]) for column in table["columns"]}
        image = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
        values = {
            ids["Модель"]: "iPhone 17",
            ids["Количество"]: 3,
            ids["Дата приёмки"]: "2026-09-06",
            ids["Фото"]: image,
            ids["Штрих-код"]: "123456789012",
            ids["QR"]: "warehouse:item:123",
        }
        created = self.client.post(f"/warehouse/tables/{table['id']}/rows", headers=owner, json={"values": values})
        self.assertEqual(created.status_code, 201, created.text)
        row = created.json()
        self.assertEqual(row["values"][ids["Модель"]], "iPhone 17")
        self.assertEqual(row["values"][ids["Количество"]], 3)
        self.assertEqual(row["values"][ids["Дата приёмки"]], "2026-09-06")
        self.assertEqual(row["values"][ids["Фото"]], image)
        self.assertEqual(row["values"][ids["Штрих-код"]]["value"], "123456789012")
        self.assertEqual(row["values"][ids["QR"]]["value"], "warehouse:item:123")
        self.assertTrue(row["values"][ids["Штрих-код"]]["image"].startswith("data:image/svg+xml;base64,"))
        self.assertTrue(row["values"][ids["QR"]]["image"].startswith("data:image/svg+xml;base64,"))

        listed = self.client.get("/warehouse/tables", headers=owner).json()
        self.assertEqual(listed[0]["row_count"], 1)
        fetched = self.client.get(f"/warehouse/tables/{table['id']}", headers=owner).json()
        self.assertEqual(fetched["rows"][0]["id"], row["id"])

        preview = self.client.post("/warehouse/codes/preview", headers=owner, json={"kind": "qrcode", "value": "preview-value"})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["image"].startswith("data:image/svg+xml;base64,"))

    def test_validation_rejects_wrong_values(self):
        owner = self.register("Owner", "owner@example.com")
        table = self.create_table(owner)
        ids = {column["name"]: str(column["id"]) for column in table["columns"]}
        url = f"/warehouse/tables/{table['id']}/rows"
        cases = [
            ({ids["Количество"]: "not-number"}, "number"),
            ({ids["Дата приёмки"]: "06.09.2026"}, "date"),
            ({ids["Фото"]: "https://example.com/photo.jpg"}, "image"),
            ({ids["Штрих-код"]: "кириллица"}, "barcode"),
            ({"999999": "unknown"}, "unknown"),
        ]
        for values, label in cases:
            with self.subTest(label=label):
                response = self.client.post(url, headers=owner, json={"values": values})
                self.assertEqual(response.status_code, 422, response.text)

    def test_tables_and_rows_are_private_and_deletable(self):
        first = self.register("First", "first@example.com")
        second = self.register("Second", "second@example.com")
        table = self.create_table(first)
        column_id = str(table["columns"][0]["id"])
        row = self.client.post(f"/warehouse/tables/{table['id']}/rows", headers=first, json={"values": {column_id: "Private"}}).json()

        self.assertEqual(self.client.get("/warehouse/tables", headers=second).json(), [])
        self.assertEqual(self.client.get(f"/warehouse/tables/{table['id']}", headers=second).status_code, 404)
        self.assertEqual(self.client.delete(f"/warehouse/tables/{table['id']}/rows/{row['id']}", headers=second).status_code, 404)
        self.assertEqual(self.client.delete(f"/warehouse/tables/{table['id']}", headers=second).status_code, 404)

        self.assertEqual(self.client.delete(f"/warehouse/tables/{table['id']}/rows/{row['id']}", headers=first).status_code, 204)
        self.assertEqual(self.client.get(f"/warehouse/tables/{table['id']}", headers=first).json()["row_count"], 0)
        self.assertEqual(self.client.delete(f"/warehouse/tables/{table['id']}", headers=first).status_code, 204)
        self.assertEqual(self.client.get("/warehouse/tables", headers=first).json(), [])


if __name__ == "__main__":
    unittest.main()
