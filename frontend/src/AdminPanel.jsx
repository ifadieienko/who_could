import { useEffect, useState } from 'react';
import { api } from './api';
import { Badge } from './components/Badge.jsx';
import { Button } from './components/Button.jsx';
import { Field } from './components/Field.jsx';
import './admin.css';

const emptyUser = { name: '', email: '', password: '', role_ids: [] };
const emptyRole = { name: '', description: '' };

export function AdminPanel({ currentUser, onCurrentUser }) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [newUser, setNewUser] = useState(emptyUser);
  const [newRole, setNewRole] = useState(emptyRole);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const run = async (action, success) => {
    setLoading(true);
    setError('');
    try {
      const result = await action();
      if (success) setMessage(success);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const load = async () => {
    const data = await run(async () => {
      const [nextUsers, nextRoles] = await Promise.all([api.adminUsers(), api.adminRoles()]);
      return { nextUsers, nextRoles };
    });
    if (data) {
      setUsers(data.nextUsers);
      setRoles(data.nextRoles);
    }
  };

  useEffect(() => { load(); }, []);

  const submitUser = async (event) => {
    event.preventDefault();
    const created = await run(() => api.createUser(newUser), 'Пользователь создан');
    if (created) {
      setUsers((items) => [...items, created]);
      setNewUser(emptyUser);
    }
  };

  const submitRole = async (event) => {
    event.preventDefault();
    const created = await run(() => api.createRole({ name: newRole.name, description: newRole.description || null }), 'Роль создана');
    if (created) {
      setRoles((items) => [...items, created].sort((a, b) => a.name.localeCompare(b.name)));
      setNewRole(emptyRole);
    }
  };

  const toggleCreateRole = (roleId, checked) => {
    setNewUser((value) => ({
      ...value,
      role_ids: checked ? [...new Set([...value.role_ids, roleId])] : value.role_ids.filter((id) => id !== roleId)
    }));
  };

  const toggleUserRole = async (item, role, checked) => {
    const currentIds = item.roles.map((entry) => entry.id);
    const roleIds = checked ? [...new Set([...currentIds, role.id])] : currentIds.filter((id) => id !== role.id);
    const updated = await run(() => api.setUserRoles(item.id, roleIds), 'Роли обновлены');
    if (updated) {
      setUsers((items) => items.map((entry) => entry.id === updated.id ? updated : entry));
      if (updated.id === currentUser.id) onCurrentUser(updated);
    }
  };

  const removeUser = async (item) => {
    if (!window.confirm(`Удалить пользователя ${item.name}? Его задания и отклики также будут удалены.`)) return;
    const deleted = await run(async () => { await api.deleteUser(item.id); return true; }, 'Пользователь удалён');
    if (deleted) setUsers((items) => items.filter((entry) => entry.id !== item.id));
  };

  return <div className="admin-grid">
    <section className="manage-card admin-create-card">
      <div className="admin-heading"><div><p className="eyebrow">Администрирование</p><h2>Создать пользователя</h2></div></div>
      <form className="admin-form" onSubmit={submitUser}>
        <Field label="Имя"><input minLength="2" value={newUser.name} onChange={(e) => setNewUser({...newUser, name:e.target.value})} required /></Field>
        <Field label="Email"><input type="email" value={newUser.email} onChange={(e) => setNewUser({...newUser, email:e.target.value})} required /></Field>
        <Field label="Пароль"><input type="password" minLength="8" value={newUser.password} onChange={(e) => setNewUser({...newUser, password:e.target.value})} required /></Field>
        <div className="role-picker"><strong>Начальные роли</strong>{roles.filter((role) => role.name !== 'user').map((role) => <label key={role.id} className="role-check"><input type="checkbox" checked={newUser.role_ids.includes(role.id)} onChange={(e) => toggleCreateRole(role.id, e.target.checked)} /> <span>{role.name}</span></label>)}</div>
        <Button disabled={loading}>Создать пользователя</Button>
      </form>
    </section>

    <section className="manage-card admin-create-card">
      <div className="admin-heading"><div><p className="eyebrow">RBAC</p><h2>Создать роль</h2></div></div>
      <form className="admin-form" onSubmit={submitRole}>
        <Field label="Код роли" hint="Латиница, цифры, _ и -"><input minLength="2" maxLength="50" pattern="[A-Za-z][A-Za-z0-9_-]*" value={newRole.name} onChange={(e) => setNewRole({...newRole, name:e.target.value})} required /></Field>
        <Field label="Описание"><textarea maxLength="300" value={newRole.description} onChange={(e) => setNewRole({...newRole, description:e.target.value})} /></Field>
        <Button disabled={loading}>Создать роль</Button>
      </form>
      <div className="role-summary">{roles.map((role) => <Badge key={role.id} tone={role.is_system ? 'blue' : undefined}>{role.name}</Badge>)}</div>
    </section>

    <section className="manage-card admin-users-card">
      <div className="admin-heading"><div><p className="eyebrow">Пользователи</p><h2>Управление аккаунтами</h2></div><strong>{users.length}</strong></div>
      {(message || error) && <div className="admin-status">{message && <span className="notice">{message}</span>}{error && <span className="error">{error}</span>}</div>}
      {users.map((item) => <article key={item.id} className="admin-user-row">
        <div className="admin-user-meta"><strong>{item.name}</strong><small>{item.email}</small><div className="role-picker compact">{roles.map((role) => {
          const checked = item.roles.some((entry) => entry.id === role.id);
          const locked = role.name === 'user' || (item.id === currentUser.id && role.name === 'admin');
          return <label key={role.id} className="role-check"><input type="checkbox" checked={checked} disabled={locked || loading} onChange={(e) => toggleUserRole(item, role, e.target.checked)} /> <span>{role.name}</span></label>;
        })}</div></div>
        <Button variant="secondary" disabled={item.id === currentUser.id || loading} onClick={() => removeUser(item)}>Удалить</Button>
      </article>)}
      {!users.length && <p className="empty">Пользователей пока нет.</p>}
    </section>
  </div>;
}
