import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label, perms } from "../forms/editor-options.js";
import { useEffect, useState } from "react";

export function Team({ user }) {
  const [members, setMembers] = useState([]),
    [roles, setRoles] = useState([]),
    [form, setForm] = useState({
      name: "",
      email: "",
      password: "",
      role_id: "",
    }),
    [role, setRole] = useState({
      name: "",
      scope: "all",
      permissions: ["orders.read"],
    });
  const a = useAction();
  const load = async () => {
    const [m, r] = await Promise.all([call("/v2/members"), call("/v2/roles")]);
    setMembers(m);
    setRoles(r.roles);
  };
  useEffect(() => {
    a.run(load);
  }, []);
  const change = async (m, p) => {
    await call("/v2/members/" + m.id, {
      method: "PATCH",
      body: { role_id: m.role_id, active: m.active, ...p },
    });
    await load();
  };
  return (
    <>
      <h1>Команда мастерской</h1>
      <ErrorBox error={a.error} />
      <section className="w-panel">
        <table className="w-table">
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th>Роль</th>
              <th>Доступ</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>
                  {m.name}
                  <small>{m.email}</small>
                </td>
                <td>
                  <select
                    disabled={m.owner || a.busy}
                    value={m.role_id}
                    onChange={(e) =>
                      a.run(() =>
                        change(m, { role_id: Number(e.target.value) }),
                      )
                    }
                  >
                    {roles
                      .filter((r) => !r.owner || m.owner)
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                  </select>
                </td>
                <td>
                  <Button
                    secondary
                    disabled={m.owner || m.id === user.id || a.busy}
                    onClick={() =>
                      a.run(() => change(m, { active: !m.active }))
                    }
                  >
                    {m.active ? "Отключить" : "Включить"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="w-muted">
          Отключение доступа сохраняет историю сотрудника и все заказы.
        </p>
      </section>
      <div className="w-grid">
        <form
          className="w-panel"
          onSubmit={(e) => {
            e.preventDefault();
            a.run(async () => {
              await call("/v2/members", {
                method: "POST",
                body: { ...form, role_id: Number(form.role_id) },
              });
              setForm({ name: "", email: "", password: "", role_id: "" });
              await load();
            });
          }}
        >
          <h2>Добавить сотрудника</h2>
          {[
            ["name", "Имя", "text"],
            ["email", "Email", "email"],
            ["password", "Начальный пароль (от 12 символов)", "password"],
          ].map(([k, l, t]) => (
            <Field key={k} label={l}>
              <input
                required
                type={t}
                minLength={k === "password" ? 12 : 2}
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            </Field>
          ))}
          <Field label="Роль">
            <select
              required
              value={form.role_id}
              onChange={(e) => setForm({ ...form, role_id: e.target.value })}
            >
              <option value="">Выберите</option>
              {roles
                .filter((r) => !r.owner)
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
            </select>
          </Field>
          <Button disabled={a.busy}>Создать аккаунт</Button>
        </form>
        <form
          className="w-panel"
          onSubmit={(e) => {
            e.preventDefault();
            a.run(async () => {
              const { id, ...body } = role;
              await call("/v2/roles" + (id ? "/" + id : ""), {
                method: id ? "PUT" : "POST",
                body,
              });
              setRole({ name: "", scope: "all", permissions: ["orders.read"] });
              await load();
            });
          }}
        >
          <h2>Права роли</h2>
          <select
            aria-label="Редактировать роль"
            value={role.id || ""}
            onChange={(e) => {
              const r = roles.find((r) => r.id === Number(e.target.value));
              setRole(
                r
                  ? {
                      id: r.id,
                      name: r.name,
                      scope: r.scope,
                      permissions: r.permissions,
                    }
                  : { name: "", scope: "all", permissions: ["orders.read"] },
              );
            }}
          >
            <option value="">Новая роль</option>
            {roles
              .filter((r) => !r.owner)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
          </select>
          <Field label="Название">
            <input
              required
              value={role.name}
              onChange={(e) => setRole({ ...role, name: e.target.value })}
            />
          </Field>
          <Field label="Область заказов">
            <select
              value={role.scope}
              onChange={(e) => setRole({ ...role, scope: e.target.value })}
            >
              <option value="all">Вся мастерская</option>
              <option value="own">Свои и свободные</option>
            </select>
          </Field>
          <div className="w-check-grid">
            {perms.map((p) => (
              <label key={p} className="w-check">
                <input
                  type="checkbox"
                  checked={role.permissions.includes(p)}
                  onChange={(e) =>
                    setRole({
                      ...role,
                      permissions: e.target.checked
                        ? [...role.permissions, p]
                        : role.permissions.filter((x) => x !== p),
                    })
                  }
                />
                {label(p)}
              </label>
            ))}
          </div>
          <Button disabled={a.busy}>Сохранить роль</Button>
        </form>
      </div>
    </>
  );
}
