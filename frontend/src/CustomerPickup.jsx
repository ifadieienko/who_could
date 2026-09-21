import { useEffect, useState } from 'react';
import { api } from './api';
import { Button } from './components/Button.jsx';
import { OrderModal } from './MasterBoard.jsx';
import './service-board.css';

export function CustomerPickup({ user }) {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    if (!user) return;
    setLoading(true);
    setError('');
    try { setItems(await api.customerPickup()); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [user?.id]);

  const issue = async (item) => {
    if (!window.confirm(`Подтвердить выдачу заказа #${item.order.id} клиенту?`)) return;
    setLoading(true);
    setError('');
    try {
      await api.issueCustomerPickup(item.id);
      setItems((current) => current.filter((entry) => entry.id !== item.id));
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  if (!user) return <section className="manage-card service-login"><h2>Выдача клиенту</h2><p className="empty">Войдите, чтобы видеть готовые к выдаче устройства.</p></section>;

  return <div className="pickup-page">
    <section className="manage-card pickup-header"><div><p className="eyebrow">Финальный этап</p><h2>Выдача клиенту</h2><p>Устройства, которые мастер переместил в «Возврат устройства клиенту».</p></div><strong>{items.length}</strong></section>
    {error && <div className="error service-error">{error}</div>}
    <section className="pickup-grid">
      {items.map((item) => <article className="manage-card pickup-card" key={item.id}>
        <div className="pickup-card-head"><div><span>Заказ #{item.order.id}</span><strong>{item.order.form_name}</strong></div><b>Готов к выдаче</b></div>
        <div className="pickup-preview">
          {(item.order.fields || []).filter((field) => field.field_type !== 'image').slice(0, 3).map((field) => <div key={field.id}><small>{field.name}</small><span>{displayValue(item.order.values?.[String(field.id)])}</span></div>)}
        </div>
        <small>Готов с: {formatDateTime(item.ready_at)}</small>
        <div className="pickup-actions"><Button variant="secondary" onClick={() => setSelected(item.order)}>Открыть заказ</Button><Button disabled={loading} onClick={() => issue(item)}>Выдан клиенту</Button></div>
      </article>)}
      {!items.length && <section className="manage-card service-empty pickup-empty">Готовых к выдаче устройств пока нет.</section>}
    </section>
    {selected && <OrderModal order={selected} onClose={() => setSelected(null)} />}
  </div>;
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  return String(value).slice(0, 120);
}

function formatDateTime(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('ru-RU');
}
