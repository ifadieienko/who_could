import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label } from "../forms/editor-options.js";
import { t } from "../../app/i18n.js";
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
        <h1>{t("authHeadline")}</h1>
        <p>{t("authDescription")}</p>
      </div>
      <form className="w-panel" onSubmit={submit}>
        <h2>{register ? t("authRegister") : t("authLoginTitle")}</h2>
        <ErrorBox error={a.error} />
        {register && (
          <>
            <Field label={t("authName")}>
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label={t("authOrganization")}>
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
        <Field label={t("authPassword")}>
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
          {register ? t("authStart") : t("authLogin")}
        </Button>
        <Button secondary type="button" onClick={() => setRegister(!register)}>
          {register ? t("authExisting") : t("authNew")}
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
            {t("authRecover")}
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
        <h1>{t("authNewPassword")}</h1>
        <ErrorBox error={a.error} />
        {done ? (
          <a href="/">{t("authLoginNewPassword")}</a>
        ) : (
          <>
            <input
              aria-label={t("authNewPassword")}
              type="password"
              minLength="12"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button disabled={a.busy}>{t("save")}</Button>
          </>
        )}
      </form>
    </div>
  );
}
