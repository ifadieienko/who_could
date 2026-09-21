import { session } from './session';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
  });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { throw new ApiError('Сервер вернул некорректный ответ', response.status); }
  if (!response.ok) {
    if (response.status === 401) session.clear();
    throw new ApiError(typeof data?.detail === 'string' ? data.detail : 'Запрос не выполнен', response.status);
  }
  return data;
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });
const sessionProbe = async () => {
  try { return await request('/me'); }
  catch (error) { if (error.status === 401) return null; throw error; }
};
export const api = {
  register: (body) => request('/auth/register', json('POST', body)),
  login: (body) => request('/auth/login', json('POST', body)),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: sessionProbe,
  jobs: (params = {}, signal) => request(`/jobs?${new URLSearchParams(Object.entries(params).filter(([, value]) => value)).toString()}`, { signal }),
  createJob: (body) => request('/jobs', json('POST', body)),
  apply: (id, body) => request(`/jobs/${id}/applications`, json('POST', body)),
  dashboard: () => request('/dashboard'),
  setJobStatus: (id, status) => request(`/jobs/${id}/status`, json('PATCH', { status })),
  setApplicationStatus: (id, status) => request(`/applications/${id}/status`, json('PATCH', { status })),
  deviceIntakeForms: () => request('/device-intake/forms'),
  createDeviceIntakeForm: (body) => request('/device-intake/forms', json('POST', body)),
  deleteDeviceIntakeForm: async (id) => { await request(`/device-intake/forms/${id}`, { method: 'DELETE' }); return true; },
  deviceIntakeOrders: () => request('/device-intake/orders'),
  deviceIntakeOrder: (id) => request(`/device-intake/orders/${id}`),
  createDeviceIntakeOrder: (body) => request('/device-intake/orders', json('POST', body)),
  updateDeviceIntakeOrder: (id, body) => request(`/device-intake/orders/${id}`, json('PUT', body)),
  serviceBoard: () => request('/device-intake/service/board'),
  createServiceColumn: (name) => request('/device-intake/service/columns', json('POST', { name })),
  renameServiceColumn: (id, name) => request(`/device-intake/service/columns/${id}`, json('PUT', { name })),
  deleteServiceColumn: async (id) => { await request(`/device-intake/service/columns/${id}`, { method: 'DELETE' }); return true; },
  moveServiceOrder: (orderId, columnId) => request(`/device-intake/service/orders/${orderId}/column`, json('PUT', { column_id: columnId })),
  customerPickup: () => request('/device-intake/service/pickup'),
  issueCustomerPickup: (id) => request(`/device-intake/service/pickup/${id}/issue`, { method: 'PATCH' }),
  warehouseTables: () => request('/warehouse/tables'),
  warehouseTable: (id) => request(`/warehouse/tables/${id}`),
  createWarehouseTable: (body) => request('/warehouse/tables', json('POST', body)),
  deleteWarehouseTable: async (id) => { await request(`/warehouse/tables/${id}`, { method: 'DELETE' }); return true; },
  createWarehouseRow: (tableId, values) => request(`/warehouse/tables/${tableId}/rows`, json('POST', { values })),
  updateWarehouseRow: (tableId, rowId, values) => request(`/warehouse/tables/${tableId}/rows/${rowId}`, json('PUT', { values })),
  deleteWarehouseRow: async (tableId, rowId) => { await request(`/warehouse/tables/${tableId}/rows/${rowId}`, { method: 'DELETE' }); return true; },
  previewWarehouseCode: (kind, value) => request('/warehouse/codes/preview', json('POST', { kind, value })),
  adminUsers: () => request('/admin/users'),
  createUser: (body) => request('/admin/users', json('POST', body)),
  deleteUser: (id) => request(`/admin/users/${id}`, { method: 'DELETE' }),
  adminRoles: () => request('/admin/roles'),
  createRole: (body) => request('/admin/roles', json('POST', body)),
  setUserRoles: (id, roleIds) => request(`/admin/users/${id}/roles`, json('PUT', { role_ids: roleIds }))
};
