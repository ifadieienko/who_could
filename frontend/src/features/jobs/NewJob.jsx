import { useEffect, useState } from "react";
import { call } from "../../repair-api.js";
import { go } from "../../app/navigation.js";
import { t } from "../../app/i18n.js";
import {
  Field,
  Button,
  ErrorBox,
  useAction,
} from "../../components/workshop/ui.jsx";
import { CustomerPicker } from "../customers/CustomerPicker.jsx";
import { PriorityField, RelatedPicker } from "./JobFields.jsx";

export function NewJob({ can }) {
  const [templates, setTemplates] = useState([]),
    [flows, setFlows] = useState([]);
  const [form, setForm] = useState({
    customer_id: null,
    asset_id: null,
    site_id: null,
    job_type: "repair",
    priority: "normal",
    description: "",
    template_id: "",
    workflow_id: "",
    stage_forms: {},
  });
  const action = useAction();
  const allowed =
    can("jobs.create") && can("customers.read") && can("assets.read");
  useEffect(() => {
    let active = true;
    if (allowed)
      action.run(async () => {
        const [ts, ws] = await Promise.all([
          call("/v2/templates"),
          call("/v2/workflows"),
        ]);
        if (!active) return;
        const published = ts.filter((x) => x.published && !x.archived);
        setTemplates(published);
        setFlows(ws);
        setForm((f) => ({
          ...f,
          template_id: published.find((x) => x.purpose === "intake")?.id || "",
          workflow_id: ws[0]?.id || "",
        }));
      });
    return () => {
      active = false;
    };
  }, [allowed]);
  const update = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  if (!allowed) return <ErrorBox error={t("jobAccessDenied")} />;
  const workflow = flows.find((x) => x.id === Number(form.workflow_id));
  return (
    <>
      <header className="w-page-head">
        <h1>{t("newAssetJob")}</h1>
        <Button secondary onClick={() => go("/orders")}>
          {t("cancel")}
        </Button>
      </header>
      <form
        className="w-panel"
        onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => {
            const job = await call("/v2/jobs", {
              method: "POST",
              body: {
                ...form,
                template_id: Number(form.template_id),
                workflow_id: Number(form.workflow_id),
                draft: true,
              },
            });
            go("/orders/" + job.id);
          });
        }}
      >
        <ErrorBox error={action.error} />
        <fieldset disabled={action.busy}>
          <CustomerPicker
            value={form.customer_id}
            onChange={(value) =>
              setForm((f) => ({
                ...f,
                customer_id: value || null,
                asset_id: null,
                site_id: null,
              }))
            }
          />
          {form.customer_id && (
            <div key={form.customer_id} className="w-grid">
              <RelatedPicker
                kind="assets"
                customerId={form.customer_id}
                value={form.asset_id}
                onChange={(value) => update("asset_id", value)}
              />
              <RelatedPicker
                kind="sites"
                customerId={form.customer_id}
                value={form.site_id}
                onChange={(value) => update("site_id", value)}
              />
            </div>
          )}
          <p className="w-muted">{t("jobExistingHint")}</p>
          <div className="w-grid">
            <Field label={t("jobType")}>
              <select
                value={form.job_type}
                onChange={(e) => update("job_type", e.target.value)}
              >
                {["repair", "inspection", "maintenance"].map((type) => (
                  <option key={type} value={type}>
                    {t("jobType_" + type)}
                  </option>
                ))}
              </select>
            </Field>
            <PriorityField
              value={form.priority}
              onChange={(value) => update("priority", value)}
            />
          </div>
          <p className="w-muted">{t("jobTypeHint")}</p>
          <Field label={t("jobDescription")}>
            <textarea
              required
              maxLength={10000}
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
            />
          </Field>
          <div className="w-grid">
            <Field label={t("jobIntakeForm")}>
              <select
                required
                value={form.template_id}
                onChange={(e) => update("template_id", e.target.value)}
              >
                <option value="">—</option>
                {templates
                  .filter((x) => x.purpose === "intake")
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name} · v{x.revision}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label={t("jobWorkflow")}>
              <select
                required
                value={form.workflow_id}
                onChange={(e) => update("workflow_id", e.target.value)}
              >
                <option value="">—</option>
                {flows.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name} · v{x.revision}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          {[
            ...new Set(
              workflow?.stages.map((x) => x.form_phase).filter(Boolean) || [],
            ),
          ].map((phase) => (
            <Field
              key={phase}
              label={`${t("jobStageForm")} · ${t("jobPhase_" + phase)}`}
            >
              <select
                required
                value={form.stage_forms[phase] || ""}
                onChange={(e) =>
                  update("stage_forms", {
                    ...form.stage_forms,
                    [phase]: Number(e.target.value),
                  })
                }
              >
                <option value="">—</option>
                {templates
                  .filter((x) => x.purpose === phase)
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name} · v{x.revision}
                    </option>
                  ))}
              </select>
            </Field>
          ))}
          <Button
            disabled={
              !form.asset_id ||
              !form.customer_id ||
              !form.template_id ||
              !form.workflow_id
            }
          >
            {t("jobCreateDraft")}
          </Button>
        </fieldset>
      </form>
    </>
  );
}
