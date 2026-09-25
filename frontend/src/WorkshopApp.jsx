import { Auth, ResetPassword } from "./features/auth/Auth.jsx";
import { Billing } from "./features/billing/Billing.jsx";
import { Button, ErrorBox, useAction } from "./components/workshop/ui.jsx";
import { NewOrder } from "./features/jobs/NewOrder.jsx";
import { OrderDetail } from "./features/jobs/OrderDetail.jsx";
import { Orders } from "./features/jobs/Orders.jsx";
import { QuotePortal } from "./features/approvals/QuotePortal.jsx";
import { Team } from "./features/members/Team.jsx";
import { TemplateEditor } from "./features/forms/TemplateEditor.jsx";
import { Transfer } from "./features/data/Transfer.jsx";
import { Warehouse } from "./Warehouse.jsx";
import { WorkflowEditor } from "./features/workflows/WorkflowEditor.jsx";
import { call, getWorkshop, setWorkshop } from "./repair-api.js";
import { go } from "./app/navigation.js";
import { label } from "./features/forms/editor-options.js";
import { useEffect, useState } from "react";
import "./workshop.css";
import { Assets } from "./features/assets/Assets.jsx";
import { Customers } from "./features/customers/Customers.jsx";
import { t, setLocale } from "./app/i18n.js";
import { configureOrganization } from "./app/format.js";
import { OrganizationSettings } from "./features/organizations/Settings.jsx";

export default function WorkshopApp() {
  const [user, setUser] = useState(null),
    [shops, setShops] = useState([]),
    [selected, setSelected] = useState(getWorkshop());
  const [path, setPath] = useState(window.location.pathname),
    [loading, setLoading] = useState(true);
  const action = useAction();
  const load = async () => {
    try {
      const u = await call("/me");
      const ws = await call("/v2/workshops");
      setUser(u);
      setShops(ws);
      const requested =
        Number(new URLSearchParams(window.location.search).get("workshop")) ||
        getWorkshop();
      const id = ws.some((x) => x.id === requested) ? requested : ws[0]?.id;
      if (id) {
        setWorkshop(id);
        setSelected(id);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
    const change = () => setPath(window.location.pathname),
      cleared = () => setUser(null);
    window.addEventListener("popstate", change);
    window.addEventListener("who-could:session-cleared", cleared);
    return () => {
      window.removeEventListener("popstate", change);
      window.removeEventListener("who-could:session-cleared", cleared);
    };
  }, []);
  if (path.startsWith("/quote/"))
    return <QuotePortal token={path.split("/")[2]} />;
  if (path.startsWith("/reset/"))
    return <ResetPassword token={path.split("/")[2]} />;
  if (loading) return <div className="w-loading">Загрузка мастерской…</div>;
  if (!user) return <Auth onLogin={load} />;
  const shop = shops.find((x) => x.id === selected),
    can = (p) => shop?.permissions.includes(p);
  if (shop) {
    configureOrganization(shop);
    setLocale(shop.locale);
  }
  const nav = [
    ["/orders", "Заказы", "orders.read"],
    ["/templates", "Формы", "forms.manage"],
    ["/workflows", "Процессы", "workflows.manage"],
    ["/warehouse", "Склад", "warehouse.manage"],
    ["/team", "Команда", "members.manage"],
    ["/data", "Перенос данных", "data.export"],
    ["/billing", "Подписка", "billing.manage"],
    ["/settings", "Организация", "organization.manage"],
    ["/assets", t("assets"), "assets.read"],
    ["/customers", t("customers"), "customers.read"],
  ].filter((x) => can(x[2]));
  const logout = () =>
    action.run(async () => {
      await call("/auth/logout", { method: "POST" });
      setUser(null);
    });
  return (
    <div className="w-app">
      <aside className="w-sidebar">
        <div className="w-brand">
          W
          <span>
            Who Could<small>Рабочее место мастерской</small>
          </span>
        </div>
        <select
          aria-label="Мастерская"
          value={selected || ""}
          onChange={(e) => {
            setWorkshop(e.target.value);
            setSelected(Number(e.target.value));
            go("/orders");
          }}
        >
          {shops.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <nav>
          {nav.map(([url, name]) => (
            <button
              key={url}
              className={path.startsWith(url) ? "active" : ""}
              onClick={() => go(url)}
            >
              {name}
            </button>
          ))}
        </nav>
        <div className="w-account">
          <strong>{user.name}</strong>
          <small>{user.email}</small>
          <Button secondary onClick={logout}>
            Выйти
          </Button>
        </div>
      </aside>
      <main className="w-main" key={selected}>
        <ErrorBox error={action.error} />
        {!shop ? (
          <p>Доступ к мастерской отключён. Обратитесь к владельцу.</p>
        ) : path === "/assets" || /^\/assets\/\d+$/.test(path) ? (
          <Assets can={can} id={path.split("/")[2]} />
        ) : path === "/customers" ? (
          <Customers can={can} />
        ) : path === "/settings" ? (
          <OrganizationSettings shop={shop} onSave={load} />
        ) : path === "/templates" ? (
          <TemplateEditor />
        ) : path === "/workflows" ? (
          <WorkflowEditor />
        ) : path === "/team" ? (
          <Team user={user} />
        ) : path === "/data" ? (
          <Transfer />
        ) : path === "/billing" ? (
          <Billing />
        ) : path === "/warehouse" ? (
          <Warehouse user={user} />
        ) : path === "/orders/new" ? (
          <NewOrder can={can} />
        ) : /^\/orders\/[^/]+$/.test(path) ? (
          <OrderDetail id={path.split("/")[2]} can={can} user={user} />
        ) : (
          <Orders can={can} />
        )}
      </main>
    </div>
  );
}
