import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 에러 메시지를 사용자 친화적으로 변환
api.interceptors.response.use(
  (response) => {
    // Vercel 등에서 API 프록시 설정이 안 되어 index.html이 200으로 반환되는 현상 방어
    if (typeof response.data === 'string' && response.data.trim().toLowerCase().startsWith('<!doctype html')) {
      return Promise.reject(new Error('백엔드 API 서버에 연결할 수 없습니다. (VITE_API_URL 설정을 확인해주세요)'));
    }
    return response;
  },
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '서버와 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.';
    return Promise.reject(new Error(message));
  }
);

// Store API
export const storeApi = {
  getAll: (includeInactive = false) =>
    api.get('/stores', { params: { include_inactive: includeInactive } }),
  getById: (id: number) => api.get(`/stores/${id}`),
  create: (data: object) => api.post('/stores', data),
  update: (id: number, data: object) => api.put(`/stores/${id}`, data),
  deactivate: (id: number) => api.delete(`/stores/${id}`),
  activate: (id: number) => api.post(`/stores/${id}/activate`),
};

// Employee API
export const employeeApi = {
  getAll: (params?: { includeInactive?: boolean; employeeType?: string }) =>
    api.get('/employees', {
      params: {
        include_inactive: params?.includeInactive,
        employee_type: params?.employeeType,
      },
    }),
  getById: (id: number) => api.get(`/employees/${id}`),
  create: (data: object) => api.post('/employees', data),
  update: (id: number, data: object) => api.put(`/employees/${id}`, data),
  deactivate: (id: number) => api.delete(`/employees/${id}`),
  activate: (id: number) => api.post(`/employees/${id}/activate`),
};

// Schedule API
export const scheduleApi = {
  getAll: (params: { year: number; month: number; store_id?: number; employee_id?: number; employee_type?: string }) =>
    api.get('/schedules', { params }),
  generate: (year: number, month: number) =>
    api.post('/schedules/generate', null, { params: { year, month } }),
  update: (id: number, data: object) => api.put(`/schedules/${id}`, data),
  cancel: (id: number, reason?: string) =>
    api.delete(`/schedules/${id}`, { params: { reason } }),
  confirm: (id: number) => api.post(`/schedules/${id}/confirm`),
  lock: (id: number) => api.post(`/schedules/${id}/lock`),
  validate: (year: number, month: number) =>
    api.get('/schedules/validate', { params: { year, month } }),
};

// Staff Requirements API
export const requirementsApi = {
  get: (storeId: number, year: number, month: number) =>
    api.get(`/stores/${storeId}/requirements/${year}/${month}`),
  upsert: (storeId: number, year: number, month: number, data: object) =>
    api.put(`/stores/${storeId}/requirements/${year}/${month}`, data),
};

// Availability API
export const availabilityApi = {
  get: (empId: number, year: number, month: number) =>
    api.get(`/employees/${empId}/availability/${year}/${month}`),
  upsert: (empId: number, year: number, month: number, data: object) =>
    api.put(`/employees/${empId}/availability/${year}/${month}`, data),
  getExceptions: (empId: number, year: number, month: number) =>
    api.get(`/employees/${empId}/exceptions/${year}/${month}`),
};

// Work Pattern API
export const workPatternApi = {
  get: (employeeId: number) => api.get(`/employees/${employeeId}/work-patterns`),
  upsert: (employeeId: number, data: object) =>
    api.put(`/employees/${employeeId}/work-patterns`, data),
};

// Payroll API
export const payrollApi = {
  getAll: (year: number, month: number) =>
    api.get(`/payroll/${year}/${month}`),
  getStoreSummary: (year: number, month: number) =>
    api.get(`/payroll/${year}/${month}/store-summary`),
  getFinalizeStatus: (year: number, month: number) =>
    api.get(`/payroll/${year}/${month}/finalize-status`),
  finalize: (year: number, month: number) =>
    api.post(`/payroll/${year}/${month}/finalize`),
};

// Seed API (개발용)
export const seedApi = {
  run: () => api.post('/seed'),
};
