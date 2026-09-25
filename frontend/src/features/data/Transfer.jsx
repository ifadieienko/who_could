import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call, download } from "../../repair-api.js";
import { label } from "../forms/editor-options.js";
import { useEffect, useState } from "react";

export function Transfer() {
  const [templates, setTemplates] = useState([]),
    [flows, setFlows] = useState([]),
    [template, setTemplate] = useState(""),
    [workflow, setWorkflow] = useState(""),
    [kind, setKind] = useState("orders"),
    [file, setFile] = useState(null),
    [result, setResult] = useState(null);
  const a = useAction();
  useEffect(() => {
    a.run(async () => {
      const [t, w] = await Promise.all([
        call("/v2/templates"),
        call("/v2/workflows"),
      ]);
      setTemplates(t.filter((x) => x.published && x.purpose === "intake"));
      setFlows(w);
      setTemplate(t.find((x) => x.published && x.purpose === "intake")?.id);
      setWorkflow(w[0]?.id);
    });
  }, []);
  const send = (dry) =>
    a.run(async () => {
      const body = new FormData();
      body.append("file", file);
      body.append("template_id", template);
      body.append("workflow_id", workflow);
      body.append("kind", kind);
      body.append("dry_run", String(dry));
      setResult(await call("/v2/import/csv", { method: "POST", body }));
    });
  const sample = () => {
    const blob = new Blob(
      [
        "external_id,customer_external_id,name,email,phone,model,serial,problem,condition,accessories,location\norder-1,client-1,Jan Kowalski,jan@example.com,123456789,ThinkPad X1,SN123,Не включается,Царапины,Зарядка,B-12\n",
      ],
      { type: "text/csv;charset=utf-8" },
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "orders-import-example.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  return (
    <>
      <h1>Импорт и экспорт</h1>
      <ErrorBox error={a.error} />
      <div className="w-grid">
        <section className="w-panel">
          <h2>Импорт CSV</h2>
          <p>
            UTF-8, разделитель — запятая, до 1000 строк. Повторные external_id
            пропускаются. Заказы создаются в черновиках.
          </p>
          <Button secondary onClick={sample}>
            Скачать пример CSV
          </Button>
          <Field label="Тип данных">
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setResult(null);
              }}
            >
              <option value="orders">Заказы</option>
              <option value="customers">Клиенты</option>
            </select>
          </Field>
          <Field label="Форма">
            <select
              value={template}
              onChange={(e) => {
                setTemplate(e.target.value);
                setResult(null);
              }}
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Процесс">
            <select
              value={workflow}
              onChange={(e) => {
                setWorkflow(e.target.value);
                setResult(null);
              }}
            >
              {flows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="CSV файл">
            <input
              type="file"
              accept=".csv"
              onChange={(e) => {
                setFile(e.target.files[0]);
                setResult(null);
              }}
            />
          </Field>
          <div className="w-actions">
            <Button
              secondary
              disabled={!file || a.busy}
              onClick={() => send(true)}
            >
              Проверить файл
            </Button>
            <Button
              disabled={a.busy || !result?.valid || !result?.dry_run}
              onClick={() => send(false)}
            >
              Импортировать
            </Button>
          </div>
          {result && (
            <div className="w-notice">
              <p>
                {result.dry_run ? "Проверка" : "Импорт завершён"}:{" "}
                {result.created} новых, {result.skipped} пропущено.
              </p>
              {result.errors.map((e, i) => (
                <p key={i}>
                  Строка {e.line}: {e.message}
                </p>
              ))}
            </div>
          )}
        </section>
        <section className="w-panel">
          <h2>Полный экспорт</h2>
          <p>
            ZIP: клиенты, устройства, заказы, шаблоны, процессы, сметы, оплаты,
            история, склад и фотографии. Пароли и секретные ссылки не
            включаются.
          </p>
          <Button
            disabled={a.busy}
            onClick={() =>
              a.run(() => download("/v2/export", "workshop-export.zip"))
            }
          >
            Скачать архив мастерской
          </Button>
          <p className="w-muted">
            Доступен после окончания подписки. CSV-импорт и архив экспорта имеют
            разные форматы.
          </p>
        </section>
      </div>
    </>
  );
}
