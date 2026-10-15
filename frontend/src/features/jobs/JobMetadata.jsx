import { useEffect, useState } from "react";
import { call } from "../../repair-api.js";
import { t } from "../../app/i18n.js";
import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { PriorityField, RelatedPicker } from "./JobFields.jsx";

export function JobMetadata({ id, version, can, onSaved }) {
  const [job, setJob] = useState(null),
    [priority, setPriority] = useState("normal"),
    [site, setSite] = useState(null),
    [loadError, setLoadError] = useState("");
  const action = useAction();
  useEffect(() => {
    let active = true;
    setJob(null);
    action.setError("");
    setLoadError("");
    call("/v2/jobs/" + id)
      .then((data) => {
        if (active) {
          setJob(data);
          setPriority(data.priority);
          setSite(data.site_id);
        }
      })
      .catch((e) => active && setLoadError(e.message));
    return () => {
      active = false;
    };
  }, [id, version]);
  if (!job)
    return (
      <>
        <ErrorBox error={loadError} />
        <p>{t("loading")}</p>
      </>
    );
  const editable =
    can("jobs.edit") && !["issued", "cancelled"].includes(job.status);
  return (
    <section className="w-panel" aria-label={t("jobMetadata")}>
      <h2>{t("jobMetadata")}</h2>
      <ErrorBox error={action.error} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => {
            const body = { version: job.version, priority };
            if (can("customers.read")) body.site_id = site;
            await call("/v2/jobs/" + id, { method: "PATCH", body });
            await onSaved();
          });
        }}
      >
        <div className="w-grid">
          <Field label={t("jobType")}>
            <input
              value={
                ["repair", "inspection", "maintenance"].includes(job.job_type)
                  ? t("jobType_" + job.job_type)
                  : job.job_type
              }
              readOnly
            />
          </Field>
          <PriorityField
            value={priority}
            onChange={setPriority}
            disabled={!editable || action.busy}
          />
          {can("customers.read") && job.customer_id && (
            <RelatedPicker
              key={`${id}-${version}`}
              kind="sites"
              customerId={job.customer_id}
              value={site}
              onChange={setSite}
              disabled={!editable || action.busy}
            />
          )}
        </div>
        {editable && (
          <Button disabled={action.busy}>{t("jobSaveMetadata")}</Button>
        )}
      </form>
    </section>
  );
}
