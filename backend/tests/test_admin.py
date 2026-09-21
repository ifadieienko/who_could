import os
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.security import SESSION_COOKIE_NAME


class AdminApiTest(unittest.TestCase):
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
        return response.json()["user"], {"Cookie": f"{SESSION_COOKIE_NAME}={token}", "Origin": "http://testserver"}

    def register_admin(self):
        previous = os.environ.get("WHO_COULD_BOOTSTRAP_ADMIN_EMAIL")
        os.environ["WHO_COULD_BOOTSTRAP_ADMIN_EMAIL"] = "admin@example.com"
        try:
            user, headers = self.register("Admin", "admin@example.com")
        finally:
            if previous is None:
                os.environ.pop("WHO_COULD_BOOTSTRAP_ADMIN_EMAIL", None)
            else:
                os.environ["WHO_COULD_BOOTSTRAP_ADMIN_EMAIL"] = previous
        self.assertEqual({role["name"] for role in user["roles"]}, {"admin", "user"})
        return user, headers

    def test_non_admin_cannot_manage_users_or_roles(self):
        _, user_headers = self.register("Regular", "regular@example.com")
        self.assertEqual(self.client.get("/admin/users", headers=user_headers).status_code, 403)
        self.assertEqual(self.client.get("/admin/roles", headers=user_headers).status_code, 403)
        self.assertEqual(self.client.post("/admin/roles", headers=user_headers, json={"name": "moderator"}).status_code, 403)

    def test_admin_can_create_user_create_role_assign_role_and_delete_user(self):
        _, admin_headers = self.register_admin()
        existing, _ = self.register("Existing", "existing@example.com")

        role_response = self.client.post(
            "/admin/roles",
            headers=admin_headers,
            json={"name": "Moderator", "description": "Can moderate marketplace content"},
        )
        self.assertEqual(role_response.status_code, 201, role_response.text)
        role = role_response.json()
        self.assertEqual(role["name"], "moderator")
        self.assertFalse(role["is_system"])

        assigned = self.client.put(
            f"/admin/users/{existing['id']}/roles",
            headers=admin_headers,
            json={"role_ids": [role["id"]]},
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual({item["name"] for item in assigned.json()["roles"]}, {"moderator", "user"})

        created = self.client.post(
            "/admin/users",
            headers=admin_headers,
            json={"name": "Created by admin", "email": "created@example.com", "password": "password123", "role_ids": [role["id"]]},
        )
        self.assertEqual(created.status_code, 201, created.text)
        created_user = created.json()
        self.assertEqual({item["name"] for item in created_user["roles"]}, {"moderator", "user"})

        users = self.client.get("/admin/users", headers=admin_headers)
        self.assertEqual(users.status_code, 200)
        self.assertIn("created@example.com", {item["email"] for item in users.json()})

        deleted = self.client.delete(f"/admin/users/{created_user['id']}", headers=admin_headers)
        self.assertEqual(deleted.status_code, 204, deleted.text)
        users_after = self.client.get("/admin/users", headers=admin_headers).json()
        self.assertNotIn("created@example.com", {item["email"] for item in users_after})

    def test_admin_cannot_delete_self_or_remove_own_admin_role(self):
        admin, admin_headers = self.register_admin()
        self.assertEqual(self.client.delete(f"/admin/users/{admin['id']}", headers=admin_headers).status_code, 409)
        response = self.client.put(f"/admin/users/{admin['id']}/roles", headers=admin_headers, json={"role_ids": []})
        self.assertEqual(response.status_code, 409)

    def test_unknown_role_id_is_rejected(self):
        _, admin_headers = self.register_admin()
        user, _ = self.register("Target", "target@example.com")
        response = self.client.put(f"/admin/users/{user['id']}/roles", headers=admin_headers, json={"role_ids": [999999]})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
