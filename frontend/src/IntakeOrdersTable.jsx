import { useEffect, useMemo, useState } from 'react';
import { Button } from './components/Button.jsx';

const statusText = {
  deferred: 'Отложен — ждём информацию / части от клиента',
  accepted: 'Передан мастеру',
};

const normalizeName = (value) => String(value || '').trim().toLocaleLowerCase('ru-RU');
const columnKey = (field) => `${normalizeName(field.name)}::${field.field_type}`;

export function IntakeOrdersTable({ userId, forms, orders, loading, onContinue }) {
  const storageKey = `who-could:intake-orders:hidden-columns:${userId}`;
  const [hiddenColumns, setHiddenColumns] = useState(() => readHiddenColumns(storageKey));
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    setHiddenColumns(readHiddenColumns(storageKey));
  }, [storageKey]);

  const columns = useMemo(() => {
    const byKey = new Map();
    const collect = (field) => {
      const key = columnKey(field);
      if (!byKey.has(key)) byKey.set(key, { key, name: field.name, field_type: field.field_type });
    };
    forms.forEach((form) => form.fields.forEach(collect));
    orders.forEach((order) => order.fields.forEach(collect));
    return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  }, [forms, orders]);

  const visibleColumns = columns.filter((column) => !hiddenColumns.has(column.key));

  const saveHidden = (next) => {
    setHiddenColumns(next);
    try { localStorage.setItem(storageKey, JSON.stringify([...next])); } catch { /* browser storage may be unavailable */ }
  };

  const toggleColumn = (key) => {
    const next = new Set(hiddenColumns);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    saveHidden(next);
  };

  const showAll = () => saveHidden(new Set());
  const hideAll = () => saveHidden(new Set(columns.map((column) => column.key)));

  return <section className="manage-card intake-orders-table-card">
    <div className="intake-heading intake-orders-table-heading">
      <div>
        <p className="eyebrow">Все заказы</p>
        <h2>Таблица приёмки</h2>
        <p className="intake-help">Колонки собраны из полей всех форм приёмки. Ненужные поля можно скрыть.</p>
      </div>
      <div className="intake-table-tools">
        <span className="intake-table-column-count">{visibleColumns.length} / {columns.length} полей</span>
        <Button type="button" variant="secondary" onClick={() => setSettingsOpen((value) => !value)}>
          {settingsOpen ? 'Скрыть настройку' : 'Колонки'}
        </Button>
      </div>
    </div>

    {settingsOpen && <div className="intake-column-picker">
      <div className="intake-column-picker-head">
        <strong>Показывать колонки</strong>
        <div><button type="button" onClick={showAll}>Показать все</button><button type="button" onClick={hideAll}>Скрыть все</button></div>
      </div>
      {!columns.length && <span className="empty">Пользовательских колонок пока нет.</span>}
      <div className="intake-column-options">
        {columns.map((column) => <label key={column.key}>
          <input type="checkbox" checked={!hiddenColumns.has(column.key)} onChange={() => toggleColumn(column.key)} />
          <span>{column.name}</span>
          <small>{typeLabel(column.field_type)}</small>
        </label>)}
      </div>
    </div>}

    {!orders.length ? <p className="empty">Заказов пока нет. Нажмите «Новый заказ», чтобы начать приёмку.</p> : <div className="intake-table-scroll">
      <table className="intake-orders-table">
        <thead>
          <tr>
            <th>№</th>
            <th>Форма</th>
            <th>Статус</th>
            {visibleColumns.map((column) => <th key={column.key}>{column.name}<small>{typeLabel(column.field_type)}</small></th>)}
            <th>Обновлён</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => <tr className={`intake-table-row ${order.status}`} key={order.id}>
            <td className="intake-table-id">#{order.id}</td>
            <td><strong>{order.form_name}</strong></td>
            <td><span className={`intake-table-status ${order.status}`}>{statusText[order.status] || order.status}</span></td>
            {visibleColumns.map((column) => <td key={column.key}>{renderOrderCell(order, column)}</td>)}
            <td className="intake-table-date">{formatDate(order.updated_at)}</td>
            <td className="intake-table-action">
              {order.status === 'deferred'
                ? <Button type="button" variant="secondary" disabled={loading} onClick={() => onContinue(order)}>Продолжить</Button>
                : <span className="intake-forward-note">У мастера</span>}
            </td>
          </tr>)}
        </tbody>
      </table>
    </div>}
  </section>;
}

function renderOrderCell(order, column) {
  const field = order.fields.find((item) => columnKey(item) === column.key);
  if (!field) return <span className="intake-empty-value">—</span>;
  const value = order.values?.[String(field.id)];
  if (value === null || value === undefined || value === '') return <span className="intake-empty-value">Не заполнено</span>;
  if (column.field_type === 'image') return <img className="intake-table-image" src={value} alt={column.name} />;
  if (column.field_type === 'date') return <span>{formatOnlyDate(value)}</span>;
  return <span>{String(value)}</span>;
}

function typeLabel(type) {
  return ({ string: 'string', number: 'number', date: 'date', image: 'image' })[type] || type;
}

function readHiddenColumns(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || '[]');
    return new Set(Array.isArray(value) ? value : []);
  } catch {
    return new Set();
  }
}

function formatDate(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('ru-RU');
}

function formatOnlyDate(value) {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString('ru-RU');
}
