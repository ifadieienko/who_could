import os
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.security import SESSION_COOKIE_NAME


class ServiceBoardApiTest(unittest.TestCase):
    def setUp(self):
        from app.database import clear_db
        clear_db()
        self.client = TestClient(app)
        self.client.cookies.clear()

    def register(self, name, email):
        response = self.client.post('/auth/register', json={'name': name, 'email': email, 'password': 'password123'})
        self.assertEqual(response.status_code, 201, response.text)
        token = response.cookies.get(SESSION_COOKIE_NAME)
        user = response.json()['user']
        self.client.cookies.clear()
        return user, {'Cookie': f'{SESSION_COOKIE_NAME}={token}', 'Origin': 'http://testserver'}

    def admin(self):
        previous = os.environ.get('WHO_COULD_BOOTSTRAP_ADMIN_EMAIL')
        os.environ['WHO_COULD_BOOTSTRAP_ADMIN_EMAIL'] = 'admin@example.com'
        try:
            result = self.register('Admin', 'admin@example.com')
        finally:
            if previous is None:
                os.environ.pop('WHO_COULD_BOOTSTRAP_ADMIN_EMAIL', None)
            else:
                os.environ['WHO_COULD_BOOTSTRAP_ADMIN_EMAIL'] = previous
        return result

    def make_master(self, user_id, admin_headers):
        roles = self.client.get('/admin/roles', headers=admin_headers).json()
        role = next((item for item in roles if item['name'] == 'master'), None)
        if role is None:
            response = self.client.post('/admin/roles', headers=admin_headers, json={'name': 'master', 'description': 'Repair master'})
            self.assertEqual(response.status_code, 201, response.text)
            role = response.json()
        response = self.client.put(f'/admin/users/{user_id}/roles', headers=admin_headers, json={'role_ids': [role['id']]})
        self.assertEqual(response.status_code, 200, response.text)

    def accepted_order(self, owner_headers):
        form_response = self.client.post('/device-intake/forms', headers=owner_headers, json={
            'name': 'Ремонт ноутбука',
            'fields': [
                {'name': 'Модель устройства', 'field_type': 'string'},
                {'name': 'Описание неисправности', 'field_type': 'string'},
            ],
        })
        self.assertEqual(form_response.status_code, 201, form_response.text)
        form = form_response.json()
        values = {
            str(form['fields'][0]['id']): 'ThinkPad X1',
            str(form['fields'][1]['id']): 'Не включается после падения',
        }
        response = self.client.post('/device-intake/orders', headers=owner_headers, json={
            'form_id': form['id'], 'values': values, 'status': 'accepted',
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_master_claim_move_terminal_and_pickup(self):
        _, admin_headers = self.admin()
        owner, owner_headers = self.register('Reception', 'reception@example.com')
        master, master_headers = self.register('Master', 'master@example.com')
        second, second_headers = self.register('Second', 'second@example.com')
        self.make_master(master['id'], admin_headers)
        self.make_master(second['id'], admin_headers)
        order = self.accepted_order(owner_headers)

        board = self.client.get('/device-intake/service/board', headers=master_headers)
        self.assertEqual(board.status_code, 200, board.text)
        data = board.json()
        self.assertEqual([item['id'] for item in data['incoming']], [order['id']])
        self.assertEqual(data['columns'][-1]['name'], 'Возврат устройства клиенту')
        self.assertTrue(data['columns'][-1]['is_terminal'])

        first_column = data['columns'][0]
        claimed = self.client.put(
            f"/device-intake/service/orders/{order['id']}/column",
            headers=master_headers,
            json={'column_id': first_column['id']},
        )
        self.assertEqual(claimed.status_code, 200, claimed.text)
        self.assertEqual(claimed.json()['column_id'], first_column['id'])

        second_board = self.client.get('/device-intake/service/board', headers=second_headers).json()
        self.assertEqual(second_board['incoming'], [])
        conflict = self.client.put(
            f"/device-intake/service/orders/{order['id']}/column",
            headers=second_headers,
            json={'column_id': second_board['columns'][0]['id']},
        )
        self.assertEqual(conflict.status_code, 409)

        terminal = data['columns'][-1]
        completed = self.client.put(
            f"/device-intake/service/orders/{order['id']}/column",
            headers=master_headers,
            json={'column_id': terminal['id']},
        )
        self.assertEqual(completed.status_code, 200, completed.text)

        pickup = self.client.get('/device-intake/service/pickup', headers=owner_headers)
        self.assertEqual(pickup.status_code, 200, pickup.text)
        self.assertEqual(len(pickup.json()), 1)
        self.assertEqual(pickup.json()[0]['order']['id'], order['id'])
        pickup_id = pickup.json()[0]['id']

        issued = self.client.patch(f'/device-intake/service/pickup/{pickup_id}/issue', headers=owner_headers)
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertEqual(issued.json()['status'], 'issued')
        self.assertEqual(self.client.get('/device-intake/service/pickup', headers=owner_headers).json(), [])

    def test_access_and_column_management(self):
        _, admin_headers = self.admin()
        regular, regular_headers = self.register('Regular', 'regular@example.com')
        master, master_headers = self.register('Master', 'master@example.com')
        self.make_master(master['id'], admin_headers)

        self.assertEqual(self.client.get('/device-intake/service/board', headers=regular_headers).status_code, 403)
        board = self.client.get('/device-intake/service/board', headers=master_headers).json()
        terminal = board['columns'][-1]

        created = self.client.post('/device-intake/service/columns', headers=master_headers, json={'name': 'Ожидание запчастей'})
        self.assertEqual(created.status_code, 201, created.text)
        column = created.json()
        renamed = self.client.put(f"/device-intake/service/columns/{column['id']}", headers=master_headers, json={'name': 'Ждём запчасти'})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()['name'], 'Ждём запчасти')
        self.assertEqual(self.client.delete(f"/device-intake/service/columns/{column['id']}", headers=master_headers).status_code, 204)
        self.assertEqual(self.client.delete(f"/device-intake/service/columns/{terminal['id']}", headers=master_headers).status_code, 409)
        self.assertEqual(self.client.put(f"/device-intake/service/columns/{terminal['id']}", headers=master_headers, json={'name': 'Финиш'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
