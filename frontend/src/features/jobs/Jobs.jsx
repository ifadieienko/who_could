import { useEffect, useState } from "react";
import { call } from "../../repair-api.js";
import {
  Field,
  Button,
  ErrorBox,
  useAction,
} from "../../components/workshop/ui.jsx";
import { t } from "../../app/i18n.js";
import { go } from "../../app/navigation.js";
import { localToISO, time } from "../../app/format.js";

export function Jobs({ can }) {
  const [data, setData] = useState({ items: [], total: 0 }),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(1);
  const action = useAction();
  useEffect(() => {
    const controller = new AbortController();
    call("/v2/jobs?" + new URLSearchParams({ q: query, page }), {
      signal: controller.signal,
    })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") action.setError(e.message);
      });
    return () => controller.abort();
  }, [query, page]);
  return (
    <section>
      <div className="w-page-head">
        <h1>
          {t("jobs")} · {data.total}
        </h1>
        {can("jobs.create") && (
          <Button onClick={() => go("/jobs/new")}>{t("newJob")}</Button>
        )}
      </div>
      <ErrorBox error={action.error} />
      <Field label={t("search")}>
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
      </Field>
      {data.items.map((job) => (
        <article key={job.id} className="w-panel">
          <h2>
            #{job.number} · {job.model}
          </h2>
          <p>{job.description}</p>
          <p>
            {job.stage_name} · {t(job.priority)} · {time(job.due_at)}
          </p>
          <Button secondary onClick={() => go("/jobs/" + job.id)}>
            {t("open")}
          </Button>
        </article>
      ))}
      {page > 1 && (
        <Button secondary onClick={() => setPage(page - 1)}>
          {t("back")}
        </Button>
      )}
      {page * 30 < data.total && (
        <Button onClick={() => setPage(page + 1)}>{t("more")}</Button>
      )}
    </section>
  );
}

export function NewJob() {
  const [assets, setAssets] = useState([]),
    [query, setQuery] = useState(""),
    [templates, setTemplates] = useState([]),
    [workflows, setWorkflows] = useState([]),
    [selectedAsset, setSelectedAsset] = useState(null);
  const [form, setForm] = useState({
    asset_id:
      Number(new URLSearchParams(window.location.search).get("asset")) || "",
    template_id: "",
    workflow_id: "",
    description: "",
    job_type: "repair",
    priority: "normal",
    due_at: "",
  });
  const action = useAction();
  useEffect(() => {
    action.run(async () => {
      const [forms, flows] = await Promise.all([
        call("/v2/templates"),
        call("/v2/workflows"),
      ]);
      setTemplates(forms.filter((f) => f.published && f.purpose === "intake"));
      setWorkflows(flows);
      setForm((old) => ({
        ...old,
        template_id:
          forms.find((f) => f.published && f.purpose === "intake")?.id || "",
        workflow_id: flows[0]?.id || "",
      }));
    });
  }, []);
  useEffect(() => {
    const c = new AbortController();
    call("/v2/assets?q=" + encodeURIComponent(query), { signal: c.signal })
      .then((r) => setAssets(r.items.filter((a) => a.status === "active")))
      .catch((e) => {
        if (e.name !== "AbortError") action.setError(e.message);
      });
    return () => c.abort();
  }, [query]);
  useEffect(() => {
    if (form.asset_id)
      action.run(async () =>
        setSelectedAsset(await call("/v2/assets/" + form.asset_id)),
      );
  }, [form.asset_id]);
  const options =
    selectedAsset && !assets.some((a) => a.id === selectedAsset.id)
      ? [selectedAsset, ...assets]
      : assets;
  const field = (k) => ({
    value: form[k],
    onChange: (e) => setForm({ ...form, [k]: e.target.value }),
  });
  return (
    <form
      className="w-panel"
      onSubmit={(e) => {
        e.preventDefault();
        action.run(async () => {
          const job = await call("/v2/jobs", {
            method: "POST",
            body: {
              ...form,
              asset_id: Number(form.asset_id),
              template_id: Number(form.template_id),
              workflow_id: Number(form.workflow_id),
              due_at: localToISO(form.due_at),
              draft: true,
            },
          });
          go("/jobs/" + job.id);
        });
      }}
    >
      <h1>{t("newJob")}</h1>
      <ErrorBox error={action.error} />
      <Field label={t("search")}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} />
      </Field>
      <Field label={t("assets")}>
        <select required {...field("asset_id")}>
          <option value="">—</option>
          {options.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name || a.model} · {a.serial}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("intakeForm")}>
        <select required {...field("template_id")}>
          <option value="">—</option>
          {templates.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name} · v{f.revision}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("workflow")}>
        <select required {...field("workflow_id")}>
          <option value="">—</option>
          {workflows.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name} · v{f.revision}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("description")}>
        <textarea required maxLength={10000} {...field("description")} />
      </Field>
      <Field label={t("jobType")}>
        <select {...field("job_type")}>
          {["repair", "inspection", "calibration"].map((k) => (
            <option key={k} value={k}>
              {t(k)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("priority")}>
        <select {...field("priority")}>
          {["low", "normal", "high", "urgent"].map((k) => (
            <option key={k} value={k}>
              {t(k)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("dueAt")}>
        <input type="datetime-local" {...field("due_at")} />
      </Field>
      <Button disabled={action.busy}>{t("create")}</Button>
      <Button secondary type="button" onClick={() => go("/jobs")}>
        {t("cancel")}
      </Button>
    </form>
  );
}
