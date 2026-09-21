import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { Badge } from './components/Badge.jsx';
import { Button } from './components/Button.jsx';
import { Field } from './components/Field.jsx';
import { IntakeOrdersTable } from './IntakeOrdersTable.jsx';
import './device-intake.css';

const emptyField = () => ({ name: '', field_type: 'string' });
const FIELD_TYPES = [
  ['string', 'string'],
  ['number', 'number'],
  ['date', 'date'],
  ['image', 'фото / картинка'],
];

export function DeviceIntake({ user }) {
  const [forms, setForms] = useState([]);
  const [orders, setOrders] = useState([]);
  const [name, setName] = useState('');
  const [fields, setFields] = useState([emptyField()]);
  const [orderOpen, setOrderOpen] = useState(false);
  const [editingOrder, setEditingOrder] = useState(null);
  const [selectedFormId, setSelectedFormId] = useState('');
  const [orderValues, setOrderValues] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const run = async (action, success) => {
    setLoading(true);
    setError('');
    setMessage('');
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

  const load = async () => {
    if (!user) return;
    const data = await run(() => Promise.all([api.deviceIntakeForms(), api.deviceIntakeOrders()]));
    if (!data) return;
    setForms(data[0]);
    setOrders(data[1]);
  };

  useEffect(() => { load(); }, [user?.id]);

  const addField = () => setFields((items) => [...items, emptyField()]);
  const removeField = (index) => setFields((items) => items.filter((_, itemIndex) => itemIndex !== index));
  const changeField = (index, key, value) => setFields((items) => items.map((field, itemIndex) => itemIndex === index ? { ...field, [key]: value } : field));

  const submit = async (event) => {
    event.preventDefault();
    const created = await run(() => api.createDeviceIntakeForm({ name, fields }), 'Форма приёмки создана');
    if (!created) return;
    setForms((items) => [created, ...items]);
    setName('');
    setFields([emptyField()]);
  };

  const removeForm = async (form) => {
    if (!window.confirm(`Удалить форму «${form.name}»? Уже созданные заказы сохранятся.`)) return;
    const result = await run(() => api.deleteDeviceIntakeForm(form.id), 'Форма удалена');
    if (result !== null) setForms((items) => items.filter((item) => item.id !== form.id));
  };

  const openNewOrder = () => {
    setError('');
    setMessage('');
    if (!forms.length) {
      setError('Сначала создайте хотя бы одну форму приёмки.');
      return;
    }
    setEditingOrder(null);
    setSelectedFormId(String(forms[0].id));
    setOrderValues({});
    setOrderOpen(true);
  };

  const continueOrder = (order) => {
    setError('');
    setMessage('');
    setEditingOrder(order);
    setSelectedFormId(order.form_id ? String(order.form_id) : '');
    setOrderValues(order.values || {});
    setOrderOpen(true);
  };

  const closeOrder = () => {
    setOrderOpen(false);
    setEditingOrder(null);
    setSelectedFormId('');
    setOrderValues({});
  };

  const selectedForm = useMemo(
    () => forms.find((form) => form.id === Number(selectedFormId)) || null,
    [forms, selectedFormId],
  );
  const activeOrderFields = editingOrder?.fields || selectedForm?.fields || [];
  const activeOrderName = editingOrder?.form_name || selectedForm?.name || '';

  const normalizedOrderValues = useMemo(() => Object.fromEntries(activeOrderFields.map((field) => {
    const raw = orderValues[field.id];
    if (raw === undefined || raw === '') return [String(field.id), null];
    if (field.field_type === 'number') return [String(field.id), Number(raw)];
    return [String(field.id), raw];
  })), [activeOrderFields, orderValues]);

  const saveOrder = async (status) => {
    if (!editingOrder && !selectedForm) {
      setError('Выберите форму приёмки.');
      return;
    }
    const action = editingOrder
      ? () => api.updateDeviceIntakeOrder(editingOrder.id, { values: normalizedOrderValues, status })
      : () => api.createDeviceIntakeOrder({ form_id: selectedForm.id, values: normalizedOrderValues, status });
    const saved = await run(action, status === 'deferred' ? 'Заказ отложен' : 'Устройство принято, заказ передан мастеру');
    if (!saved) return;
    setOrders((items) => editingOrder
      ? items.map((item) => item.id === saved.id ? saved : item)
      : [saved, ...items]);
    closeOrder();
  };

  const setOrderValue = (fieldId, value) => setOrderValues((current) => ({ ...current, [fieldId]: value }));

  const orderImageChanged = (field, file) => {
    if (!file) {
      setOrderValue(field.id, '');
      return;
    }
    if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) {
      setError('Поддерживаются PNG, JPEG, WEBP и GIF.');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError('Изображение должно быть не больше 5 МБ.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setOrderValue(field.id, String(reader.result || ''));
    reader.onerror = () => setError('Не удалось прочитать изображение.');
    reader.readAsDataURL(file);
  };

  if (!user) {
    return <section className="publish-form intake-login"><p className="eyebrow">Приём устройства</p><h2>Приёмка и заказы</h2><p className="empty">Войдите в аккаунт, чтобы создавать формы и оформлять приём устройств.</p></section>;
  }

  const deferredCount = orders.filter((order) => order.status === 'deferred').length;
  const acceptedCount = orders.filter((order) => order.status === 'accepted').length;

  return <div className="intake-page">
    <section className="manage-card intake-topbar">
      <div><p className="eyebrow">Приём устройства</p><h2>Заказы приёмки</h2><p>Создайте новый заказ, выберите форму и заполните данные принятого устройства.</p></div>
      <div className="intake-topbar-actions">
        <span className="intake-order-counts"><b>{deferredCount}</b> отложено · <b>{acceptedCount}</b> передано мастеру</span>
        <Button onClick={openNewOrder}>+ Новый заказ</Button>
      </div>
    </section>

    {(message || error) && <div className="intake-global-status">{message && <span className="notice">{message}</span>}{error && <span className="error">{error}</span>}</div>}

    {orderOpen && <section className="manage-card intake-order-editor">
      <div className="intake-heading">
        <div><p className="eyebrow">{editingOrder ? `Заказ #${editingOrder.id}` : 'Новый заказ'}</p><h2>{activeOrderName || 'Выберите форму'}</h2></div>
        <Button type="button" variant="ghost" onClick={closeOrder}>Закрыть</Button>
      </div>

      {!editingOrder && <Field label="Форма приёмки" hint="Шаблон данных устройства">
        <select value={selectedFormId} onChange={(e) => { setSelectedFormId(e.target.value); setOrderValues({}); }}>
          {forms.map((form) => <option value={form.id} key={form.id}>{form.name}</option>)}
        </select>
      </Field>}

      {editingOrder && !editingOrder.form_id && <p className="intake-snapshot-note">Исходный шаблон был удалён. Заказ открыт по сохранённому снимку формы.</p>}

      <div className="intake-order-fields">
        {activeOrderFields.map((field) => <IntakeOrderField
          key={field.id}
          field={field}
          value={orderValues[field.id]}
          onValue={setOrderValue}
          onImage={orderImageChanged}
        />)}
        {!activeOrderFields.length && <p className="empty">В выбранной форме нет полей.</p>}
      </div>

      <div className="intake-order-actions">
        <div><strong>Отложить</strong><small>Можно сохранить даже с незаполненными полями и продолжить позже.</small></div>
        <Button type="button" variant="secondary" disabled={loading} onClick={() => saveOrder('deferred')}>Отложить</Button>
        <Button type="button" disabled={loading} onClick={() => saveOrder('accepted')}>Принять</Button>
      </div>
    </section>}

    <IntakeOrdersTable
      userId={user.id}
      forms={forms}
      orders={orders}
      loading={loading}
      onContinue={continueOrder}
    />

    <div className="intake-layout">
      <section className="manage-card intake-builder">
        <div className="intake-heading"><div><p className="eyebrow">Настройка</p><h2>Создать форму</h2></div><Badge tone="blue">{fields.length} полей</Badge></div>
        <p className="intake-help">Добавляйте столько полей, сколько нужно. Доступны текст, число, дата и фото/картинка.</p>
        <form onSubmit={submit}>
          <Field label="Название формы"><input maxLength="120" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Приём смартфона" required /></Field>
          <div className="intake-fields">
            {fields.map((field, index) => <div className="intake-field-row" key={index}>
              <span className="intake-index">{index + 1}</span>
              <input maxLength="120" value={field.name} onChange={(e) => changeField(index, 'name', e.target.value)} placeholder="Название поля" required />
              <select value={field.field_type} onChange={(e) => changeField(index, 'field_type', e.target.value)}>
                {FIELD_TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
              <Button type="button" variant="ghost" onClick={() => removeField(index)}>Удалить</Button>
            </div>)}
          </div>
          <div className="intake-actions"><Button type="button" variant="secondary" onClick={addField}>+ Добавить поле</Button><Button disabled={loading}>Сохранить форму</Button></div>
        </form>
      </section>

      <section className="manage-card intake-saved">
        <div className="intake-heading"><div><p className="eyebrow">Шаблоны</p><h2>Мои формы</h2></div><strong>{forms.length}</strong></div>
        {!forms.length && <p className="empty">Форм пока нет. Создайте первую слева.</p>}
        {forms.map((form) => <article className="intake-form-card" key={form.id}>
          <div className="intake-form-head"><div><strong>{form.name}</strong><small>{form.fields.length} полей</small></div><Button variant="ghost" disabled={loading} onClick={() => removeForm(form)}>Удалить</Button></div>
          <div className="intake-preview">
            {form.fields.map((field) => <IntakePreviewField key={field.id} field={field} />)}
            {!form.fields.length && <p className="empty">В этой форме пока нет полей.</p>}
          </div>
        </article>)}
      </section>
    </div>
  </div>;
}

function IntakeOrderField({ field, value, onValue, onImage }) {
  if (field.field_type === 'image') {
    return <Field label={field.name} hint="Фото / картинка">
      <div className="intake-image-preview">
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(e) => onImage(field, e.target.files?.[0])} />
        {value && <img src={value} alt={field.name} />}
      </div>
    </Field>;
  }
  if (field.field_type === 'date') return <Field label={field.name} hint="Дата"><input type="date" value={value || ''} onChange={(e) => onValue(field.id, e.target.value)} /></Field>;
  if (field.field_type === 'number') return <Field label={field.name} hint="Число"><input type="number" value={value ?? ''} onChange={(e) => onValue(field.id, e.target.value)} /></Field>;
  return <Field label={field.name} hint="Текст"><input type="text" value={value || ''} onChange={(e) => onValue(field.id, e.target.value)} placeholder="Введите значение" /></Field>;
}

function IntakePreviewField({ field }) {
  const [image, setImage] = useState('');

  if (field.field_type === 'image') {
    const onImage = (event) => {
      const file = event.target.files?.[0];
      if (!file) {
        setImage('');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => setImage(String(reader.result || ''));
      reader.readAsDataURL(file);
    };
    return <Field label={field.name} hint="image"><div className="intake-image-preview"><input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={onImage} />{image && <img src={image} alt={`Предпросмотр: ${field.name}`} />}</div></Field>;
  }

  if (field.field_type === 'date') return <Field label={field.name} hint="date"><input type="date" /></Field>;
  if (field.field_type === 'number') return <Field label={field.name} hint="number"><input type="number" placeholder="0" /></Field>;
  return <Field label={field.name} hint="string"><input type="text" placeholder="Введите значение" /></Field>;
}
