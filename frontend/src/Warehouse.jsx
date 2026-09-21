import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { Badge } from './components/Badge.jsx';
import { Button } from './components/Button.jsx';
import { Field } from './components/Field.jsx';
import './warehouse.css';

const TYPES = [
  ['string', 'String'],
  ['number', 'Number'],
  ['date', 'Date'],
  ['image', 'Фото / картинка'],
  ['barcode', 'Штрих-код'],
  ['qrcode', 'QR-код'],
];

const typeLabel = Object.fromEntries(TYPES);
const emptyColumn = () => ({ name: '', field_type: 'string' });

export function Warehouse({ user }) {
  const [tables, setTables] = useState([]);
  const [active, setActive] = useState(null);
  const [tableName, setTableName] = useState('');
  const [columns, setColumns] = useState([emptyColumn()]);
  const [values, setValues] = useState({});
  const [previews, setPreviews] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const run = async (action, success) => {
    setLoading(true);
    setError('');
    try {
      const result = await action();
      if (success) setMessage(success);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const openTable = async (id) => {
    const result = await run(() => api.warehouseTable(id));
    if (result) {
      setActive(result);
      setValues({});
      setPreviews({});
    }
  };

  const load = async () => {
    if (!user) return;
    const result = await run(api.warehouseTables);
    if (!result) return;
    setTables(result);
    if (result.length) await openTable(result[0].id);
    else setActive(null);
  };

  useEffect(() => { load(); }, [user?.id]);

  const addColumn = () => setColumns((items) => [...items, emptyColumn()]);
  const removeColumn = (index) => setColumns((items) => items.filter((_, itemIndex) => itemIndex !== index));
  const changeColumn = (index, key, value) => setColumns((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));

  const createTable = async (event) => {
    event.preventDefault();
    const created = await run(() => api.createWarehouseTable({ name: tableName, columns }), 'Таблица склада создана');
    if (!created) return;
    setTables((items) => [{ id: created.id, name: created.name, columns: created.columns, row_count: 0, created_at: created.created_at }, ...items]);
    setActive(created);
    setTableName('');
    setColumns([emptyColumn()]);
    setValues({});
    setPreviews({});
  };

  const deleteTable = async () => {
    if (!active || !window.confirm(`Удалить таблицу «${active.name}» вместе со всеми строками?`)) return;
    const ok = await run(() => api.deleteWarehouseTable(active.id), 'Таблица удалена');
    if (!ok) return;
    const remaining = tables.filter((table) => table.id !== active.id);
    setTables(remaining);
    setActive(null);
    if (remaining.length) await openTable(remaining[0].id);
  };

  const normalizedValues = useMemo(() => {
    if (!active) return {};
    return Object.fromEntries(active.columns.map((column) => {
      const value = values[column.id];
      if (value === undefined || value === '') return [String(column.id), null];
      if (column.field_type === 'number') return [String(column.id), Number(value)];
      return [String(column.id), value];
    }));
  }, [active, values]);

  const addRow = async (event) => {
    event.preventDefault();
    if (!active) return;
    const row = await run(() => api.createWarehouseRow(active.id, normalizedValues), 'Позиция добавлена на склад');
    if (!row) return;
    setActive((table) => ({ ...table, rows: [...table.rows, row], row_count: table.row_count + 1 }));
    setTables((items) => items.map((table) => table.id === active.id ? { ...table, row_count: table.row_count + 1 } : table));
    setValues({});
    setPreviews({});
  };

  const deleteRow = async (rowId) => {
    if (!active || !window.confirm('Удалить эту строку склада?')) return;
    const ok = await run(() => api.deleteWarehouseRow(active.id, rowId), 'Строка удалена');
    if (!ok) return;
    setActive((table) => ({ ...table, rows: table.rows.filter((row) => row.id !== rowId), row_count: Math.max(0, table.row_count - 1) }));
    setTables((items) => items.map((table) => table.id === active.id ? { ...table, row_count: Math.max(0, table.row_count - 1) } : table));
  };

  const setValue = (columnId, value) => setValues((current) => ({ ...current, [columnId]: value }));

  const imageChanged = (column, file) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError('Изображение должно быть не больше 5 МБ');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setValue(column.id, reader.result);
    reader.onerror = () => setError('Не удалось прочитать изображение');
    reader.readAsDataURL(file);
  };

  const randomCode = (kind) => {
    const uuid = crypto.randomUUID().replaceAll('-', '').toUpperCase();
    return kind === 'barcode' ? `${Date.now()}${Math.floor(Math.random() * 1000)}` : uuid;
  };

  const previewCode = async (column, generate = false) => {
    const value = generate ? randomCode(column.field_type) : String(values[column.id] || '').trim();
    if (!value) {
      setError('Сначала введите значение для кода');
      return;
    }
    if (generate) setValue(column.id, value);
    const result = await run(() => api.previewWarehouseCode(column.field_type, value));
    if (result) setPreviews((current) => ({ ...current, [column.id]: result.image }));
  };

  if (!user) {
    return <section className="publish-form"><p className="eyebrow">Склад</p><h2>Учет товаров и устройств</h2><p className="empty">Войдите в аккаунт, чтобы создавать складские таблицы.</p></section>;
  }

  return <div className="warehouse-page">
    <aside className="warehouse-builder manage-card">
      <div className="warehouse-title"><div><p className="eyebrow">Склад</p><h2>Новая таблица</h2></div><Badge tone="blue">{columns.length} колонок</Badge></div>
      <p className="warehouse-help">Создайте структуру таблицы. Колонки могут хранить текст, числа, даты, изображения, штрих-коды и QR-коды.</p>
      <form onSubmit={createTable}>
        <Field label="Название таблицы"><input value={tableName} onChange={(e) => setTableName(e.target.value)} maxLength="120" placeholder="Например: Склад телефонов" required /></Field>
        <div className="warehouse-column-list">
          {columns.map((column, index) => <div className="warehouse-column-row" key={index}>
            <span>{index + 1}</span>
            <input value={column.name} onChange={(e) => changeColumn(index, 'name', e.target.value)} maxLength="120" placeholder="Название колонки" required />
            <select value={column.field_type} onChange={(e) => changeColumn(index, 'field_type', e.target.value)}>
              {TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
            <Button type="button" variant="ghost" onClick={() => removeColumn(index)}>×</Button>
          </div>)}
        </div>
        <div className="warehouse-actions"><Button type="button" variant="secondary" onClick={addColumn}>+ Колонка</Button><Button disabled={loading}>Создать таблицу</Button></div>
      </form>
      <div className="warehouse-table-list">
        <h3>Мои таблицы</h3>
        {!tables.length && <p className="empty">Таблиц пока нет.</p>}
        {tables.map((table) => <button type="button" className={`warehouse-table-link ${active?.id === table.id ? 'active' : ''}`} key={table.id} onClick={() => openTable(table.id)}>
          <span><strong>{table.name}</strong><small>{table.columns.length} колонок</small></span><Badge>{table.row_count}</Badge>
        </button>)}
      </div>
    </aside>

    <section className="warehouse-workspace manage-card">
      {!active ? <div className="warehouse-empty"><h2>Склад пуст</h2><p>Создайте первую таблицу слева.</p></div> : <>
        <div className="warehouse-title"><div><p className="eyebrow">Таблица склада</p><h2>{active.name}</h2><small>{active.row_count} строк · {active.columns.length} колонок</small></div><Button variant="ghost" disabled={loading} onClick={deleteTable}>Удалить таблицу</Button></div>

        <form className="warehouse-row-form" onSubmit={addRow}>
          <h3>Добавить строку</h3>
          <div className="warehouse-row-fields">
            {active.columns.map((column) => <WarehouseInput key={column.id} column={column} value={values[column.id]} preview={previews[column.id]} onValue={setValue} onImage={imageChanged} onCode={previewCode} />)}
          </div>
          <Button disabled={loading}>Добавить на склад</Button>
        </form>

        <div className="warehouse-grid-wrap">
          <table className="warehouse-grid">
            <thead><tr><th>#</th>{active.columns.map((column) => <th key={column.id}><span>{column.name}</span><small>{typeLabel[column.field_type]}</small></th>)}<th></th></tr></thead>
            <tbody>
              {active.rows.map((row, index) => <tr key={row.id}><td>{index + 1}</td>{active.columns.map((column) => <td key={column.id}><WarehouseCell column={column} value={row.values[String(column.id)]} /></td>)}<td><Button variant="ghost" disabled={loading} onClick={() => deleteRow(row.id)}>Удалить</Button></td></tr>)}
              {!active.rows.length && <tr><td colSpan={active.columns.length + 2}><p className="empty">Строк пока нет. Добавьте первую позицию выше.</p></td></tr>}
            </tbody>
          </table>
        </div>
      </>}
      {(message || error) && <div className="warehouse-status">{message && <span className="notice">{message}</span>}{error && <span className="error">{error}</span>}</div>}
    </section>
  </div>;
}

function WarehouseInput({ column, value, preview, onValue, onImage, onCode }) {
  if (column.field_type === 'image') return <Field label={column.name} hint="Фото / картинка"><div className="warehouse-image-input"><input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(e) => onImage(column, e.target.files?.[0])} />{value && <img src={value} alt="Предпросмотр" />}</div></Field>;
  if (column.field_type === 'barcode' || column.field_type === 'qrcode') return <Field label={column.name} hint={typeLabel[column.field_type]}><div className="warehouse-code-input"><input value={value || ''} onChange={(e) => onValue(column.id, e.target.value)} placeholder="Значение кода" /><div><Button type="button" variant="secondary" onClick={() => onCode(column, true)}>Сгенерировать</Button><Button type="button" variant="ghost" onClick={() => onCode(column, false)}>Предпросмотр</Button></div>{preview && <img src={preview} alt={typeLabel[column.field_type]} />}</div></Field>;
  return <Field label={column.name} hint={typeLabel[column.field_type]}><input type={column.field_type === 'number' ? 'number' : column.field_type === 'date' ? 'date' : 'text'} value={value ?? ''} onChange={(e) => onValue(column.id, e.target.value)} /></Field>;
}

function WarehouseCell({ column, value }) {
  if (value === null || value === undefined || value === '') return <span className="warehouse-null">—</span>;
  if (column.field_type === 'image') return <a href={value} target="_blank" rel="noreferrer"><img className="warehouse-thumb" src={value} alt={column.name} /></a>;
  if (column.field_type === 'barcode' || column.field_type === 'qrcode') return <div className={`warehouse-code-cell ${column.field_type}`}><img src={value.image} alt={column.name} /><small>{value.value}</small></div>;
  return <span>{String(value)}</span>;
}
