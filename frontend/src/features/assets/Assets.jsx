import { useEffect, useState } from "react";
import { call, printDocument } from "../../repair-api.js";
import {
  Field,
  Button,
  ErrorBox,
  useAction,
} from "../../components/workshop/ui.jsx";
import { CustomerPicker } from "../customers/CustomerPicker.jsx";
import { Photo } from "../../components/workshop/Photo.jsx";
import { t } from "../../app/i18n.js";
import { go } from "../../app/navigation.js";
import { time } from "../../app/format.js";
const empty = {
  customer_id: null,
  site_id: null,
  name: "",
  asset_type: "device",
  manufacturer: "",
  model: "",
  serial: "",
  external_id: "",
  status: "active",
  custom_values: {},
};
export function Assets({ can, id }) {
  const [items, setItems] = useState([]),
    [next, setNext] = useState(null),
    [query, setQuery] = useState(""),
    [asset, setAsset] = useState(null),
    [form, setForm] = useState(null);
  const action = useAction();
  const load = async (after = null) => {
    if (id) {
      setAsset(await call("/v2/assets/" + id));
      return;
    }
    const r = await call(
      "/v2/assets?q=" +
        encodeURIComponent(query) +
        (after ? "&after=" + after : ""),
    );
    setItems((old) => (after ? [...old, ...r.items] : r.items));
    setNext(r.next);
  };
  useEffect(() => {
    setAsset(null);
    setForm(null);
    action.run(() => load());
  }, [id, query]);
  const saved = async (row) => {
    setForm(null);
    if (id) setAsset(row);
    else go("/assets/" + row.id);
  };
  return (
    <section>
      <ErrorBox error={action.error} />
      {id ? (
        <>
          <Button secondary onClick={() => go("/assets")}>
            {t("back")}
          </Button>
          {asset && (
            <>
              <div className="w-page-head">
                <h1>{asset.name || asset.model}</h1>
                {can("jobs.create") && (
                  <Button onClick={() => go("/jobs/new?asset=" + asset.id)}>
                    {t("newJob")}
                  </Button>
                )}
                <Button
                  onClick={() =>
                    action.run(() => printDocument(`/v2/assets/${id}/label`))
                  }
                >
                  {t("label")}
                </Button>
              </div>
              <p>
                {asset.manufacturer} · {asset.model} · {asset.serial}
              </p>
              <p>
                {t(asset.asset_type)} · {t(asset.status)}
              </p>
              {can("assets.write") && (
                <Button
                  secondary
                  onClick={() =>
                    setForm({
                      ...Object.fromEntries(
                        Object.keys(empty).map((k) => [k, asset[k]]),
                      ),
                      id: asset.id,
                      version: asset.version,
                    })
                  }
                >
                  {t("edit")}
                </Button>
              )}
              {can("jobs.read") && (
                <>
                  <AssetHistory key={"jobs-" + id} id={id} kind="jobs" />
                  <AssetHistory key={"files-" + id} id={id} kind="files" />
                </>
              )}
            </>
          )}
        </>
      ) : (
        <>
          <div className="w-page-head">
            <h1>{t("assets")}</h1>
            {can("assets.write") && can("customers.read") && (
              <Button onClick={() => setForm({ ...empty })}>
                {t("newAsset")}
              </Button>
            )}
          </div>
          <Field label={t("search")}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
          </Field>
          {items.map((row) => (
            <article className="w-panel" key={row.id}>
              <h2>{row.name || row.model}</h2>
              <p>
                {row.manufacturer} · {row.serial}
              </p>
              <Button secondary onClick={() => go("/assets/" + row.id)}>
                {t("open")}
              </Button>
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
        </>
      )}
      {form && (
        <AssetEditor
          key={form.id || "new"}
          initial={form}
          onSave={saved}
          onCancel={() => setForm(null)}
        />
      )}
    </section>
  );
}
function AssetHistory({ id, kind }) {
  const [items, setItems] = useState([]),
    [next, setNext] = useState(null);
  const action = useAction();
  const load = async (after = null) => {
    const r = await call(
      `/v2/assets/${id}/${kind}` + (after ? "?after=" + after : ""),
    );
    setItems((old) => (after ? [...old, ...r.items] : r.items));
    setNext(r.next);
  };
  useEffect(() => {
    action.run(() => load());
  }, [id, kind]);
  return (
    <section className="w-panel">
      <h2>{t(kind === "jobs" ? "history" : "photos")}</h2>
      <ErrorBox error={action.error} />
      {kind === "jobs" ? (
        items.map((job) => (
          <p key={job.id}>
            <a
              href={"/orders/" + job.id}
              onClick={(e) => {
                e.preventDefault();
                go("/orders/" + job.id);
              }}
            >
              #{job.number} · {job.problem}
            </a>{" "}
            · {job.stage_name} · {time(job.created_at)}
          </p>
        ))
      ) : (
        <div className="w-photos">
          {items.map((file) => (
            <Photo key={file.id} file={file} />
          ))}
        </div>
      )}
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
function AssetEditor({ initial, onSave, onCancel }) {
  const [form, setForm] = useState(initial),
    [sites, setSites] = useState([]),
    [next, setNext] = useState(null);
  const action = useAction();
  const loadSites = async (after = null) => {
    if (!form.customer_id) {
      setSites([]);
      return;
    }
    const r = await call(
      "/v2/sites?customer_id=" +
        form.customer_id +
        (after ? "&after=" + after : ""),
    );
    setSites((old) => (after ? [...old, ...r.items] : r.items));
    setNext(r.next);
  };
  useEffect(() => {
    action.run(() => loadSites());
  }, [form.customer_id]);
  const field = (k) => ({
    value: form[k] || "",
    onChange: (e) => setForm({ ...form, [k]: e.target.value }),
  });
  return (
    <form
      className="w-panel"
      onSubmit={(e) => {
        e.preventDefault();
        action.run(async () => {
          const body = { ...form };
          delete body.id;
          const row = await call(
            "/v2/assets" + (form.id ? "/" + form.id : ""),
            { method: form.id ? "PATCH" : "POST", body },
          );
          await onSave(row);
        });
      }}
    >
      <h2>{form.id ? t("edit") : t("newAsset")}</h2>
      <ErrorBox error={action.error} />
      <CustomerPicker
        value={form.customer_id}
        disabled={!!form.id}
        onChange={(value) =>
          setForm({ ...form, customer_id: value, site_id: null })
        }
      />
      <Field label={t("site")}>
        <select
          value={form.site_id || ""}
          onChange={(e) =>
            setForm({ ...form, site_id: Number(e.target.value) || null })
          }
        >
          <option value="">{t("noSite")}</option>
          {sites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.name}
            </option>
          ))}
        </select>
      </Field>
      {next && (
        <Button
          type="button"
          secondary
          onClick={() => action.run(() => loadSites(next))}
        >
          {t("more")}
        </Button>
      )}
      {["name", "manufacturer", "model", "serial", "external_id"].map((k) => (
        <Field key={k} label={t(k)}>
          <input required={k === "name"} maxLength={160} {...field(k)} />
        </Field>
      ))}
      <Field label={t("asset_type")}>
        <select {...field("asset_type")}>
          {[
            "device",
            "ring",
            "necklace",
            "bracelet",
            "earrings",
            "watch",
            "instrument",
            "reference_standard",
            "other",
          ].map((k) => (
            <option key={k} value={k}>
              {t(k)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("status")}>
        <select {...field("status")}>
          {["active", "retired", "quarantined"].map((k) => (
            <option key={k} value={k}>
              {t(k)}
            </option>
          ))}
        </select>
      </Field>
      <Button disabled={action.busy}>{t("save")}</Button>
      <Button secondary type="button" onClick={onCancel}>
        {t("cancel")}
      </Button>
    </form>
  );
}
