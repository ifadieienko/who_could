import { useEffect, useState } from "react";
import { call } from "../../repair-api.js";
import {
  Field,
  Button,
  ErrorBox,
  useAction,
} from "../../components/workshop/ui.jsx";
import { t } from "../../app/i18n.js";
const empty = {
  kind: "person",
  name: "",
  company_name: "",
  tax_id: "",
  contact_person: "",
  email: "",
  phone: "",
  address: "",
};
export function Customers({ can }) {
  const [items, setItems] = useState([]),
    [next, setNext] = useState(null),
    [query, setQuery] = useState(""),
    [form, setForm] = useState(null),
    [selected, setSelected] = useState(null);
  const action = useAction();
  const load = async (after = null) => {
    const r = await call(
      "/v2/customer-records?q=" +
        encodeURIComponent(query) +
        (after ? "&after=" + after : ""),
    );
    setItems((old) => (after ? [...old, ...r.items] : r.items));
    setNext(r.next);
  };
  useEffect(() => {
    action.run(() => load());
  }, [query]);
  const save = (e) => {
    e.preventDefault();
    action.run(async () => {
      const body = { ...form, email: form.email || null };
      delete body.id;
      await call("/v2/customer-records" + (form.id ? "/" + form.id : ""), {
        method: form.id ? "PATCH" : "POST",
        body,
      });
      setForm(null);
      await load();
    });
  };
  return (
    <section>
      <div className="w-page-head">
        <h1>{t("customers")}</h1>
        {can("customers.write") && (
          <Button onClick={() => setForm({ ...empty })}>
            {t("newCustomer")}
          </Button>
        )}
      </div>
      <ErrorBox error={action.error} />
      <Field label={t("search")}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} />
      </Field>
      {form && (
        <form className="w-panel" onSubmit={save}>
          <h2>{form.id ? t("edit") : t("newCustomer")}</h2>
          <Field label={t("kind")}>
            <select
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              {["person", "company"].map((k) => (
                <option key={k} value={k}>
                  {t(k)}
                </option>
              ))}
            </select>
          </Field>
          {Object.keys(empty)
            .filter((k) => k !== "kind")
            .map((k) => (
              <Field key={k} label={t(k)}>
                <input
                  required={
                    k === "name" ||
                    (k === "company_name" && form.kind === "company")
                  }
                  type={k === "email" ? "email" : "text"}
                  value={form[k] || ""}
                  onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                />
              </Field>
            ))}
          <Button disabled={action.busy}>{t("save")}</Button>
          <Button secondary type="button" onClick={() => setForm(null)}>
            {t("cancel")}
          </Button>
        </form>
      )}
      {items.map((c) => (
        <article className="w-panel" key={c.id}>
          <h2>{c.name}</h2>
          <p>
            {c.company_name} {c.email} {c.phone}
          </p>
          <p>{c.address}</p>
          <div className="w-actions">
            {can("customers.write") && (
              <Button
                secondary
                onClick={() =>
                  setForm({
                    ...Object.fromEntries(
                      Object.keys(empty).map((k) => [k, c[k] ?? ""]),
                    ),
                    id: c.id,
                    version: c.version,
                  })
                }
              >
                {t("edit")}
              </Button>
            )}
            <Button
              secondary
              onClick={() => setSelected(selected?.id === c.id ? null : c)}
            >
              {t("sites")}
            </Button>
          </div>
          {selected?.id === c.id && <Sites key={c.id} customer={c} can={can} />}
        </article>
      ))}
      {!items.length && <p>{t("noRecords")}</p>}
      {next && (
        <Button
          disabled={action.busy}
          onClick={() => action.run(() => load(next))}
        >
          {t("more")}
        </Button>
      )}
    </section>
  );
}
function Sites({ customer, can }) {
  const [items, setItems] = useState([]),
    [next, setNext] = useState(null),
    [form, setForm] = useState(null);
  const action = useAction();
  const load = async (after = null) => {
    const r = await call(
      `/v2/sites?customer_id=${customer.id}` + (after ? "&after=" + after : ""),
    );
    setItems((old) => (after ? [...old, ...r.items] : r.items));
    setNext(r.next);
  };
  useEffect(() => {
    action.run(() => load());
  }, [customer.id]);
  return (
    <section>
      <h3>{t("sites")}</h3>
      <ErrorBox error={action.error} />
      {items.map((site) => (
        <div key={site.id}>
          <strong>{site.name}</strong>
          <p>{site.address}</p>
          {can("customers.write") && (
            <Button
              secondary
              onClick={() =>
                setForm({
                  id: site.id,
                  name: site.name,
                  address: site.address,
                  notes: site.notes,
                  version: site.version,
                })
              }
            >
              {t("edit")}
            </Button>
          )}
        </div>
      ))}
      {next && (
        <Button onClick={() => action.run(() => load(next))}>
          {t("more")}
        </Button>
      )}
      {can("customers.write") && (
        <Button
          secondary
          onClick={() => setForm({ name: "", address: "", notes: "" })}
        >
          {t("newSite")}
        </Button>
      )}
      {form && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            action.run(async () => {
              const body = { ...form, customer_id: customer.id };
              delete body.id;
              await call("/v2/sites" + (form.id ? "/" + form.id : ""), {
                method: form.id ? "PATCH" : "POST",
                body,
              });
              setForm(null);
              await load();
            });
          }}
        >
          {["name", "address", "notes"].map((k) => (
            <Field label={t(k)} key={k}>
              <input
                required={k === "name"}
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            </Field>
          ))}
          <Button disabled={action.busy}>{t("save")}</Button>
          <Button secondary type="button" onClick={() => setForm(null)}>
            {t("cancel")}
          </Button>
        </form>
      )}
    </section>
  );
}
