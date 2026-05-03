/**
 * api.js — Centralised API client
 * All fetch calls go through here. Token is automatically injected.
 */

// Auto-detect API base:
// - If served via nginx on port 80 or 8080 → use relative /api/v1 (proxy handles it)
// - If opened directly (file://) or on any other port (e.g. 5500 Live Server) → hit backend directly
const _proto = window.location.protocol;
const _port  = window.location.port;
const _isNginx = _proto !== 'file:' && (_port === '80' || _port === '8080' || (_port === '' && _proto === 'http:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'));
const API_BASE = _isNginx ? '/api/v1' : 'http://localhost:8000/api/v1';

// ── Token helpers ─────────────────────────────────────────────────────────────
export const auth = {
  getToken:   ()        => localStorage.getItem('token'),
  setToken:   (t)       => localStorage.setItem('token', t),
  getUser:    ()        => JSON.parse(localStorage.getItem('user') || 'null'),
  setUser:    (u)       => localStorage.setItem('user', JSON.stringify(u)),
  clear:      ()        => { localStorage.removeItem('token'); localStorage.removeItem('user'); },
  isLoggedIn: ()        => !!localStorage.getItem('token'),
  isAdmin:    ()        => { const u = auth.getUser(); return u && u.role === 'admin'; },
};

// ── Core fetch wrapper ────────────────────────────────────────────────────────
async function request(path, options = {}) {
  const token = auth.getToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    auth.clear();
    window.location.href = 'index.html';
    return;
  }

  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }

  if (!res.ok) {
    const msg = data?.detail
      ? (Array.isArray(data.detail) ? data.detail.map(e => e.msg).join(', ') : data.detail)
      : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

// ── Auth endpoints ────────────────────────────────────────────────────────────
export const authAPI = {
  register: (username, email, password, role = 'member') =>
    request('/auth/register', { method: 'POST', body: JSON.stringify({ username, email, password, role }) }),

  login: (username, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),

  me: () => request('/auth/me'),
};

// ── Books endpoints ───────────────────────────────────────────────────────────
export const booksAPI = {
  getAll: (skip = 0, limit = 20, search = '') => {
    const q = new URLSearchParams({ skip, limit });
    if (search) q.set('search', search);
    return request(`/books?${q}`);
  },
  getById:  (id)   => request(`/books/${id}`),
  create:   (data) => request('/books', { method: 'POST', body: JSON.stringify(data) }),
  update:   (id, data) => request(`/books/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete:   (id)   => request(`/books/${id}`, { method: 'DELETE' }),
};

// ── Borrow endpoints ──────────────────────────────────────────────────────────
export const borrowAPI = {
  getAll:    (skip = 0, limit = 20, status = '') => {
    const q = new URLSearchParams({ skip, limit });
    if (status) q.set('status', status);
    return request(`/borrow?${q}`);
  },
  getById:   (id)      => request(`/borrow/${id}`),
  borrow:    (book_id) => request('/borrow', { method: 'POST', body: JSON.stringify({ book_id }) }),
  return_:   (id)      => request(`/borrow/${id}/return`, { method: 'PUT' }),
  delete:    (id)      => request(`/borrow/${id}`, { method: 'DELETE' }),
  userBorrows: (userId, skip = 0, limit = 20) =>
    request(`/borrow/user/${userId}?skip=${skip}&limit=${limit}`),
};

// ── Dashboard / Monitoring ────────────────────────────────────────────────────
const DASHBOARD_BASE = _isNginx ? '' : 'http://localhost:8000';
export const dashboardAPI = {
  metrics: () => fetch(`${DASHBOARD_BASE}/dashboard/metrics`).then(r => r.json()),
  logs:    (lines = 30) => fetch(`${DASHBOARD_BASE}/dashboard/logs?lines=${lines}`).then(r => r.json()),
};
