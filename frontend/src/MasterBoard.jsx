import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { Button } from './components/Button.jsx';
import './service-board.css';

const PROBLEM_WORDS = ['полом', 'неисправ', 'проблем', 'дефект', 'жалоб', 'описан'];

export function MasterBoard({ user }) {
  const [board, setBoard] = useState({ columns: [], incoming: [], items: [] });
  const [selected, setSelected] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newColumn, setNewColumn] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (quiet = false) => {
    if (!user) return;
    if (!quiet) setLoading(true);
    setError('');
    try { setBoard(await api.serviceBoard()); }
    catch (e) { setError(e.message); }
    finally { if (!quiet) setLoading(false); }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 15000);
    return () => window.clearInterval(timer);
  }, [user?.id]);

  const byColumn = useMemo(() => Object.fromEntries(board.columns.map((column) => [column.id, board.items.filter((item) => item.column_id === column.id)])), [board]);

  const moveOrder = async (orderId, columnId) => {
    setLoading(true);
    setError('');
    try {
      await api.moveServiceOrder(orderId, columnId);
      await load();
    } catch (e) { setError(e.message); setLoading(false); }
  };

  const addColumn = async (event) => {
    event.preventDefault();
    if (!newColumn.trim()) return;
    setLoading(true);
    setError('');
    try { await api.createServiceColumn(newColumn.trim()); setNewColumn(''); await load(); }
    catch (e) { setError(e.message); setLoading(false); }
  };

  const renameColumn = async (column) => {
    const name = window.prompt('Новое название колонки', column.name)?.trim();
    if (!name || name === column.name) return;
    try { await api.renameServiceColumn(column.id, name); await load(); }
    catch (e) { setError(e.message); }
  };

  const removeColumn = async (column) => {
    if (!window.confirm(`Удалить колонку «${column.name}»?`)) return;
    try { await api.deleteServiceColumn(column.id); await load(); }
    catch (e) { setError(e.message); }
  };

  if (!user) return <section className="manage-card service-login"><h2>Мастер</h2><p className="empty">Войдите в аккаунт мастера.</p></section>;

  return <div className="service-page">
    <section className="manage-card service-header">
      <div><p className="eyebrow">Ремонт</p><h2>Доска мастера</h2><p>Перетаскивайте новые заказы в нужную колонку и ведите устройство до возврата клиенту.</p></div>
      <Button variant="secondary" onClick={() => setSettingsOpen((value) => !value)}>Колонки</Button>
    </section>

    {error && <div className="error service-error">{error}</div>}

    {settingsOpen && <section className="manage-card service-settings">
      <div className="service-settings-head"><div><p className="eyebrow">Настройка</p><h3>Колонки мастера</h3></div><small>Финальная колонка системная и не изменяется.</small></div>
      <div className="service-settings-list">
        {board.columns.map((column) => <div key={column.id} className="service-settings-row">
          <span>{column.name}</span>
          {column.is_terminal ? <strong>Финальная</strong> : <div><Button variant="ghost" onClick={() => renameColumn(column)}>Переименовать</Button><Button variant="ghost" onClick={() => removeColumn(column)}>Удалить</Button></div>}
        </div>)}
      </div>
      <form className="service-add-column" onSubmit={addColumn}><input maxLength="120" value={newColumn} onChange={(e) => setNewColumn(e.target.value)} placeholder="Название новой колонки"/><Button disabled={loading}>+ Добавить колонку</Button></form>
    </section>}

    <div className="service-board-shell">
      <aside className="service-inbox">
        <div className="service-inbox-head"><div><span className="service-new-dot"/><strong>Новые заказы</strong></div><b>{board.incoming.length}</b></div>
        <p>Перетащите заказ на доску, чтобы взять его в работу.</p>
        <div className="service-inbox-list">
          {board.incoming.map((order) => <OrderCard key={order.id} order={order} incoming onOpen={() => setSelected(order)} />)}
          {!board.incoming.length && <div className="service-empty">Новых заказов нет</div>}
        </div>
      </aside>

      <div className="service-columns">
        {board.columns.map((column) => <section
          className={`service-column ${column.is_terminal ? 'terminal' : ''}`}
          key={column.id}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => { event.preventDefault(); const id = Number(event.dataTransfer.getData('text/order-id')); if (id) moveOrder(id, column.id); }}
        >
          <header><div><strong>{column.name}</strong>{column.is_terminal && <small>→ Выдача клиенту</small>}</div><span>{byColumn[column.id]?.length || 0}</span></header>
          <div className="service-column-cards">
            {(byColumn[column.id] || []).map((item) => <OrderCard key={item.id} order={item.order} onOpen={() => setSelected(item.order)} locked={column.is_terminal} />)}
            {!(byColumn[column.id] || []).length && <div className="service-drop-hint">Перетащите карточку сюда</div>}
          </div>
        </section>)}
      </div>
    </div>

    {selected && <OrderModal order={selected} onClose={() => setSelected(null)} />}
  </div>;
}

function OrderCard({ order, incoming = false, locked = false, onOpen }) {
  const summary = problemSummary(order);
  return <article
    className={`service-card ${incoming ? 'incoming' : ''}`}
    draggable={!locked}
    onDragStart={(event) => { event.dataTransfer.setData('text/order-id', String(order.id)); event.dataTransfer.effectAllowed = 'move'; }}
    onClick={onOpen}
  >
    <div className="service-card-top"><span>#{order.id}</span>{incoming && <b>Новый</b>}</div>
    <strong>{deviceTitle(order)}</strong>
    <p>{summary || 'Описание неисправности не указано'}</p>
    <small>{order.form_name}</small>
  </article>;
}

export function OrderModal({ order, onClose }) {
  return <div className="service-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="service-modal" role="dialog" aria-modal="true">
      <header><div><p className="eyebrow">Заказ #{order.id}</p><h2>{deviceTitle(order)}</h2><small>{order.form_name}</small></div><Button variant="ghost" onClick={onClose}>Закрыть</Button></header>
      <div className="service-modal-grid">
        {(order.fields || []).map((field) => <div className="service-detail" key={`${field.id}-${field.name}`}><small>{field.name}</small><FullValue field={field} value={order.values?.[String(field.id)]} /></div>)}
      </div>
      <footer><span>Создан: {formatDateTime(order.created_at)}</span><span>Обновлён: {formatDateTime(order.updated_at)}</span></footer>
    </section>
  </div>;
}

function FullValue({ field, value }) {
  if (value === null || value === undefined || value === '') return <span className="service-muted">Не заполнено</span>;
  if (field.field_type === 'image') return <a href={value} target="_blank" rel="noreferrer"><img className="service-modal-image" src={value} alt={field.name}/></a>;
  if (field.field_type === 'date') return <span>{formatDate(value)}</span>;
  return <span>{String(value)}</span>;
}

function fieldValue(order, field) { return order.values?.[String(field.id)]; }

function problemSummary(order) {
  const fields = order.fields || [];
  const preferred = fields.find((field) => field.field_type === 'string' && PROBLEM_WORDS.some((word) => field.name.toLowerCase().includes(word)) && fieldValue(order, field));
  const fallback = fields.find((field) => field.field_type === 'string' && fieldValue(order, field));
  const value = preferred ? fieldValue(order, preferred) : fallback ? fieldValue(order, fallback) : '';
  return value ? String(value).slice(0, 180) : '';
}

function deviceTitle(order) {
  const fields = order.fields || [];
  const preferred = fields.find((field) => field.field_type === 'string' && /(устрой|модель|марка|бренд|телефон|ноутбук)/i.test(field.name) && fieldValue(order, field));
  return preferred ? String(fieldValue(order, preferred)).slice(0, 80) : order.form_name;
}

function formatDate(value) {
  if (!value) return '—';
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('ru-RU');
}

function formatDateTime(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('ru-RU');
}
