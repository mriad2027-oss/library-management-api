/**
 * utils.js — Shared UI helpers used across all pages
 */

// ── Toast notifications ───────────────────────────────────────────────────────
let _toastContainer = null;
function getToastContainer() {
  if (!_toastContainer) {
    _toastContainer = document.createElement('div');
    _toastContainer.id = 'toast-container';
    document.body.appendChild(_toastContainer);
  }
  return _toastContainer;
}

export function toast(message, type = 'info', duration = 3500) {
  const container = getToastContainer();
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
  el.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ'}</span><span>${message}</span>`;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    el.addEventListener('transitionend', () => el.remove(), { once: true });
  }, duration);
}

// ── Modal ─────────────────────────────────────────────────────────────────────
export function openModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) { m.classList.add('open'); document.body.style.overflow = 'hidden'; }
}
export function closeModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) { m.classList.remove('open'); document.body.style.overflow = ''; }
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.closest('.modal').classList.remove('open');
    document.body.style.overflow = '';
  }
});

// ── Guard: redirect if not logged in ─────────────────────────────────────────
export function requireAuth() {
  if (!localStorage.getItem('token')) {
    window.location.href = 'index.html';
    return false;
  }
  return true;
}

// ── Guard: redirect if already logged in ─────────────────────────────────────
export function redirectIfLoggedIn(dest = 'dashboard.html') {
  if (localStorage.getItem('token')) window.location.href = dest;
}

// ── Render nav user info ──────────────────────────────────────────────────────
export function renderNav() {
  const user = JSON.parse(localStorage.getItem('user') || 'null');
  const el = document.getElementById('nav-user');
  if (!el || !user) return;
  el.innerHTML = `
    <div class="nav-avatar">${user.username[0].toUpperCase()}</div>
    <div class="nav-user-info">
      <span class="nav-username">${user.username}</span>
      <span class="nav-role badge-${user.role}">${user.role}</span>
    </div>
    <button class="btn-icon logout-btn" id="logout-btn" title="Logout">⎋</button>
  `;
  document.getElementById('logout-btn')?.addEventListener('click', () => {
    localStorage.clear();
    window.location.href = 'index.html';
  });
}

// ── Format date ───────────────────────────────────────────────────────────────
export function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ── Spinner ───────────────────────────────────────────────────────────────────
export function showSpinner(containerId) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="spinner-wrap"><div class="spinner"></div></div>`;
}

export function setLoading(btnEl, loading, text = '') {
  if (!btnEl) return;
  btnEl.disabled = loading;
  btnEl.innerHTML = loading
    ? `<span class="btn-spinner"></span> Loading...`
    : text || btnEl.dataset.originalText || 'Submit';
  if (text) btnEl.dataset.originalText = text;
}

// ── Debounce ──────────────────────────────────────────────────────────────────
export function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ── Confirm dialog ────────────────────────────────────────────────────────────
export function confirm(message) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    overlay.innerHTML = `
      <div class="confirm-box">
        <p>${message}</p>
        <div class="confirm-actions">
          <button class="btn btn-ghost" id="confirm-no">Cancel</button>
          <button class="btn btn-danger" id="confirm-yes">Confirm</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('show'));
    const close = (val) => {
      overlay.classList.remove('show');
      overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
      resolve(val);
    };
    overlay.querySelector('#confirm-yes').onclick = () => close(true);
    overlay.querySelector('#confirm-no').onclick  = () => close(false);
  });
}
