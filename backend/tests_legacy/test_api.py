import os
import tempfile
import unittest
from pathlib import Path

TEMP = tempfile.TemporaryDirectory()
os.environ["WHO_COULD_DB"] = str(Path(TEMP.name) / "test.db")
os.environ["WHO_COULD_SECRET"] = "tests-only-secret-that-is-at-least-32-characters"

from fastapi.testclient import TestClient
from app.main import app
from app.security import SESSION_COOKIE_NAME


class MarketplaceApiTest(unittest.TestCase):
    def setUp(self):
        from app.database import clear_db
        clear_db()
        self.client = TestClient(app)
        self.client.cookies.clear()

    def register(self, name, email):
        response = self.client.post("/auth/register", json={"name": name, "email": email, "password": "password123"})
        self.assertEqual(response.status_code, 201, response.text)
        token = response.cookies.get(SESSION_COOKIE_NAME)
        self.assertTrue(token)
        self.assertNotIn("token", response.json())
        self.client.cookies.clear()
        return response.json(), {"Cookie": f"{SESSION_COOKIE_NAME}={token}", "Origin": "http://testserver"}

    def job(self, owner, **overrides):
        payload = {"title": "Собрать лендинг", "description": "Нужно собрать аккуратный лендинг для проверки MVP.", "category": "Разработка", "work_mode": "online", "duration": "short", "budget_type": "fixed", "budget_min": 100, "budget_max": 300, "currency": "usd"}
        payload.update(overrides)
        response = self.client.post("/jobs", headers=owner, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def apply(self, job_id, worker, message="Готов выполнить задачу и показать результат."):
        return self.client.post(f"/jobs/{job_id}/applications", headers=worker, json={"message": message, "proposed_rate": 200})

    def test_alembic_created_schema_and_health(self):
        from sqlalchemy import inspect, text
        from app.database import engine
        self.assertEqual(set(inspect(engine).get_table_names()), {"alembic_version", "applications", "customer_pickups", "device_intake_fields", "device_intake_forms", "device_intake_orders", "jobs", "master_board_columns", "master_work_items", "roles", "user_roles", "users", "warehouse_columns", "warehouse_rows", "warehouse_tables"})
        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "database": "ok"})
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one(), "0008_master_service_board")

    def test_session_cookie_is_http_only_same_site_and_not_in_json(self):
        response = self.client.post("/auth/register", json={"name": "Owner", "email": "owner@example.com", "password": "password123"})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("token", response.json())
        cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("max-age=86400", cookie)
        self.assertNotIn("; secure", cookie)
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_full_employer_and_performer_flow(self):
        _, owner = self.register("Owner", "owner@example.com")
        _, worker = self.register("Worker", "worker@example.com")
        job = self.job(owner)
        application = self.apply(job["id"], worker).json()
        accepted = self.client.patch(f"/applications/{application['id']}/status", headers=owner, json={"status": "accepted"})
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")
        self.assertEqual(self.client.get("/dashboard", headers=worker).json()["sent_applications"][0]["status"], "accepted")
        self.assertEqual(self.client.get(f"/jobs/{job['id']}").json()["status"], "in_progress")

    def test_auth_failures_duplicate_email_logout_and_host_guard(self):
        _, owner = self.register("Owner", "owner@example.com")
        duplicate = self.client.post("/auth/register", json={"name": "Other", "email": "OWNER@example.com", "password": "password123"})
        self.assertEqual(duplicate.status_code, 409)
        wrong = self.client.post("/auth/login", json={"email": "owner@example.com", "password": "not-the-password"})
        self.assertEqual(wrong.status_code, 401)
        for headers in ({}, {"Cookie": f"{SESSION_COOKIE_NAME}=malformed.%%%"}, {"Authorization": "Bearer old-client-token"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get("/me", headers=headers).status_code, 401)
                self.assertEqual(self.client.get("/dashboard", headers=headers).status_code, 401)
        logout = self.client.post("/auth/logout", headers=owner)
        self.assertEqual(logout.status_code, 204)
        self.assertIn("max-age=0", logout.headers.get("set-cookie", "").lower())
        self.assertEqual(self.client.get("/health", headers={"Host": "evil.example"}).status_code, 400)

    def test_cookie_authenticated_writes_require_same_origin(self):
        _, owner = self.register("Owner", "owner@example.com")
        no_origin = {"Cookie": owner["Cookie"]}
        payload = {"title": "Собрать лендинг", "description": "Нужно собрать аккуратный лендинг для проверки CSRF.", "category": "Разработка", "work_mode": "online", "duration": "short", "budget_type": "fixed", "budget_min": 100, "budget_max": 300, "currency": "USD"}
        self.assertEqual(self.client.post("/jobs", headers=no_origin, json=payload).status_code, 403)
        cross_site = {**no_origin, "Origin": "https://attacker.example"}
        self.assertEqual(self.client.post("/jobs", headers=cross_site, json=payload).status_code, 403)
        self.assertEqual(self.client.post("/jobs", headers=owner, json=payload).status_code, 201)

    def test_application_creation_rules(self):
        _, owner = self.register("Owner", "owner@example.com")
        _, worker = self.register("Worker", "worker@example.com")
        job = self.job(owner)
        self.assertEqual(self.apply(job["id"], owner).status_code, 400)
        self.assertEqual(self.apply(job["id"], worker).status_code, 201)
        self.assertEqual(self.apply(job["id"], worker).status_code, 409)
        closed_job = self.job(owner, title="Закрытая задача")
        self.assertEqual(self.client.patch(f"/jobs/{closed_job['id']}/status", headers=owner, json={"status": "closed"}).status_code, 200)
        self.assertEqual(self.apply(closed_job["id"], worker).status_code, 409)

    def test_only_owner_can_change_job_or_manage_applications(self):
        _, owner = self.register("Owner", "owner@example.com")
        _, worker = self.register("Worker", "worker@example.com")
        _, stranger = self.register("Stranger", "stranger@example.com")
        job = self.job(owner)
        application = self.apply(job["id"], worker).json()
        self.assertEqual(self.client.patch(f"/jobs/{job['id']}/status", headers=worker, json={"status": "closed"}).status_code, 403)
        self.assertEqual(self.client.patch(f"/applications/{application['id']}/status", headers=stranger, json={"status": "accepted"}).status_code, 403)

    def test_accept_is_atomic_and_terminal(self):
        _, owner = self.register("Owner", "owner@example.com")
        _, first = self.register("First", "first@example.com")
        _, second = self.register("Second", "second@example.com")
        job = self.job(owner)
        accepted_app = self.apply(job["id"], first, "Первый исполнитель готов выполнить задачу.").json()
        declined_app = self.apply(job["id"], second, "Второй исполнитель готов выполнить задачу.").json()
        accept_url = f"/applications/{accepted_app['id']}/status"
        self.assertEqual(self.client.patch(accept_url, headers=owner, json={"status": "accepted"}).status_code, 200)
        dashboard = self.client.get("/dashboard", headers=owner).json()
        statuses = {item["id"]: item["status"] for item in dashboard["received_applications"]}
        self.assertEqual(statuses, {accepted_app["id"]: "accepted", declined_app["id"]: "declined"})
        self.assertEqual(self.client.patch(accept_url, headers=owner, json={"status": "accepted"}).status_code, 409)
        self.assertEqual(self.client.patch(f"/applications/{declined_app['id']}/status", headers=owner, json={"status": "accepted"}).status_code, 409)

    def test_cannot_accept_after_job_closed(self):
        _, owner = self.register("Owner", "owner@example.com")
        _, worker = self.register("Worker", "worker@example.com")
        job = self.job(owner)
        application = self.apply(job["id"], worker).json()
        self.client.patch(f"/jobs/{job['id']}/status", headers=owner, json={"status": "closed"})
        response = self.client.patch(f"/applications/{application['id']}/status", headers=owner, json={"status": "accepted"})
        self.assertEqual(response.status_code, 409)

    def test_status_transitions_do_not_reopen(self):
        _, owner = self.register("Owner", "owner@example.com")
        job = self.job(owner)
        url = f"/jobs/{job['id']}/status"
        self.assertEqual(self.client.patch(url, headers=owner, json={"status": "in_progress"}).status_code, 200)
        self.assertEqual(self.client.patch(url, headers=owner, json={"status": "open"}).status_code, 409)
        self.assertEqual(self.client.patch(url, headers=owner, json={"status": "closed"}).status_code, 200)
        self.assertEqual(self.client.patch(url, headers=owner, json={"status": "open"}).status_code, 409)

    def test_model_validation(self):
        _, owner = self.register("Owner", "owner@example.com")
        response = self.client.post("/jobs", headers=owner, json={"title": "Неверный бюджет", "description": "Описание задачи достаточно длинное для проверки.", "category": "Тест", "work_mode": "online", "duration": "short", "budget_type": "fixed", "budget_min": 500, "budget_max": 100, "currency": "12$", "deadline": "not-a-date"})
        self.assertEqual(response.status_code, 422)
        valid = self.job(owner, title="Задача с датой", deadline="2027-01-31")
        self.assertEqual(valid["currency"], "USD")
        self.assertEqual(valid["deadline"], "2027-01-31")

    def test_dashboard_does_not_expose_other_private_applications(self):
        _, owner = self.register("Owner", "owner@example.com")
        _, worker = self.register("Worker", "worker@example.com")
        _, stranger = self.register("Stranger", "stranger@example.com")
        job = self.job(owner)
        self.apply(job["id"], worker, "Секретное сообщение настоящего исполнителя.")
        dashboard = self.client.get("/dashboard", headers=stranger).json()
        self.assertEqual(dashboard["received_applications"], [])
        self.assertEqual(dashboard["sent_applications"], [])


if __name__ == "__main__":
    unittest.main()
