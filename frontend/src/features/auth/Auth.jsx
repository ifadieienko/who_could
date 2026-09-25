import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label } from "../forms/editor-options.js";
import { useState } from "react";

export function Auth({ onLogin }) {
  const [register, setRegister] = useState(false),
    [form, setForm] = useState({
      name: "",
      email: "",
      password: "",
      workshop: "",
    }),
    [notice, setNotice] = useState("");
  const a = useAction();
  const submit = (e) => {
    e.preventDefault();
    a.run(async () => {
      await call(register ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: register ? form : { email: form.email, password: form.password },
      });
      await onLogin();
    });
  };
  return (
    <div className="w-auth">
      <div className="w-auth-intro">
        <p className="w-eyebrow">WHO COULD / WORKSHOP</p>
        <h1>
          Каждый ремонт.
          <br />
          От приёма до выдачи.
        </h1>
        <p>
          Заказы, фотографии, сметы и проверки — в одной истории устройства.
        </p>
      </div>
      <form className="w-panel" onSubmit={submit}>
        <h2>{register ? "Создать мастерскую" : "Войти в мастерскую"}</h2>
        <ErrorBox error={a.error} />
        {register && (
          <>
            <Field label="Ваше имя">
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="Название мастерской">
              <input
                required
                value={form.workshop}
                onChange={(e) => setForm({ ...form, workshop: e.target.value })}
              />
            </Field>
          </>
        )}
        <Field label="Email">
          <input
            type="email"
            required
            autoComplete="username"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>
        <Field label="Пароль">
          <input
            type="password"
            required
            minLength={register ? 12 : 1}
            autoComplete={register ? "new-password" : "current-password"}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <Button disabled={a.busy}>
          {register ? "Начать работу" : "Войти"}
        </Button>
        <Button secondary type="button" onClick={() => setRegister(!register)}>
          {register ? "Уже есть аккаунт" : "Новая мастерская"}
        </Button>
        {!register && (
          <Button
            secondary
            type="button"
            onClick={() =>
              a.run(async () => {
                const r = await call("/auth/reset-request", {
                  method: "POST",
                  body: { email: form.email },
                });
                setNotice(r.message);
              })
            }
          >
            Восстановить пароль
          </Button>
        )}
        {notice && <p>{notice}</p>}
      </form>
    </div>
  );
}

export function ResetPassword({ token }) {
  const [password, setPassword] = useState(""),
    [done, setDone] = useState(false);
  const a = useAction();
  return (
    <div className="w-public">
      <form
        className="w-panel"
        onSubmit={(e) => {
          e.preventDefault();
          a.run(async () => {
            await call("/auth/reset-password", {
              method: "POST",
              body: { token, password },
            });
            setDone(true);
          });
        }}
      >
        <h1>Новый пароль</h1>
        <ErrorBox error={a.error} />
        {done ? (
          <a href="/">Войти с новым паролем</a>
        ) : (
          <>
            <input
              aria-label="Новый пароль"
              type="password"
              minLength="12"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button disabled={a.busy}>Сохранить</Button>
          </>
        )}
      </form>
    </div>
  );
}
