/**
 * dashboard.js — Main application controller
 * Handles routing, all pages, CRUD, borrow/return
 */
import { auth, booksAPI, borrowAPI, dashboardAPI } from './api.js';
import { requireAuth, renderNav, toast, openModal, closeModal, fmtDate, debounce, confirm } from './utils.js';

if (!requireAuth()) throw new Error('Not authenticated');

// ── State ─────────────────────────────────────────────────────────────────────
const user = auth.getUser();
const isAdmin = auth.isAdmin();
let currentPage = 'overview';
let booksPage = 0, borrowsPage = 0, managePage = 0, allBorrowsPage = 0;
const LIMIT = 12;
let monitoringInterval = null;

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  setupUser();
  setupNav();
  setupMobileNav();
  showPage('overview');
  loadOverview();
}

function setupUser() {
  document.getElementById('welcome-name').textContent = user?.username || '—';
  document.getElementById('sidebar-avatar').textContent = (user?.username || '?')[0].toUpperCase();
  document.getElementById('sidebar-username').textContent = user?.username || '—';
  const roleEl = document.getElementById('sidebar-role');
  roleEl.textContent = user?.role || '—';
  roleEl.className = `user-role role-${user?.role}`;

  // Show admin nav items
  if (isAdmin) {
    document.getElementById('admin-section').style.display = 'block';
    document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'flex');
  }

  document.getElementById('logout-btn').addEventListener('click', () => {
    auth.clear(); window.location.href = 'index.html';
  });
}

function setupNav() {
  document.querySelectorAll('.nav-item[data-page]').forEach(item => {
    item.addEventListener('click', () => {
      const page = item.dataset.page;
      showPage(page);
      // Close mobile nav
      document.getElementById('sidebar').classList.remove('open');
    });
  });
}

function setupMobileNav() {
  document.getElementById('nav-toggle')?.addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });
}

function showPage(name) {
  currentPage = name;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`page-${name}`)?.classList.add('active');
  document.querySelector(`.nav-item[data-page="${name}"]`)?.classList.add('active');

  if (monitoringInterval) { clearInterval(monitoringInterval); monitoringInterval = null; }

  switch (name) {
    case 'overview':   loadOverview(); break;
    case 'books':      booksPage = 0; loadBooks(); break;
    case 'borrows':    borrowsPage = 0; loadMyBorrows(); break;
    case 'manage':     managePage = 0; loadManage(); break;
    case 'users':      allBorrowsPage = 0; loadAllBorrows(); break;
    case 'monitoring': loadMonitoring(); monitoringInterval = setInterval(loadMonitoring, 30000); break;
  }
}

// ── OVERVIEW ──────────────────────────────────────────────────────────────────
function setStat(id, val) {
  const el = document.getElementById(id);
  if (el) { el.textContent = val; el.classList.remove('skeleton'); }
}

async function safeCall(fn) {
  try { return await fn(); } catch { return null; }
}

async function loadOverview() {
  setStat('stat-books', '…');
  setStat('stat-available', '…');
  setStat('stat-active', '…');
  setStat('stat-overdue', '…');
  setStat('stat-mine', '…');

  const [booksData, allBorrows, myBorrows] = await Promise.all([
    safeCall(() => booksAPI.getAll(0, 1)),
    isAdmin ? safeCall(() => borrowAPI.getAll(0, 1, '')) : Promise.resolve(null),
    safeCall(() => borrowAPI.getAll(0, 5, '')),
  ]);

  const totalBooks = booksData?.total || 0;
  setStat('stat-books', totalBooks);

  const availableRes = await safeCall(() => booksAPI.getAll(0, 100));
  const available = (availableRes?.books || []).filter(b => b.available_copies > 0).length;
  setStat('stat-available', available);

  const borrows = myBorrows?.borrows || [];
  const active  = borrows.filter(b => b.status === 'active').length;
  const overdue = borrows.filter(b => b.status === 'overdue').length;

  setStat('stat-active',  isAdmin ? (allBorrows?.total ?? '0') : active);
  setStat('stat-overdue', overdue);
  setStat('stat-mine',    myBorrows?.total ?? 0);

  renderRecentBorrows(borrows);
}

function renderRecentBorrows(borrows) {
  const tbody = document.getElementById('recent-borrows-body');
  if (!borrows.length) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="empty-icon">📭</div><h3>No borrows yet</h3><p>Browse books and borrow something!</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = borrows.map(b => `
    <tr>
      <td><strong>${b.book?.title || `Book #${b.book_id}`}</strong><br/><small class="text-muted">${b.book?.author || ''}</small></td>
      <td>${fmtDate(b.borrowed_at)}</td>
      <td>${fmtDate(b.due_date)}</td>
      <td><span class="badge badge-${b.status}">${b.status}</span></td>
      <td>${b.status === 'active' ? `<button class="btn btn-sm btn-teal" onclick="window._returnBook(${b.id})">Return</button>` : '—'}</td>
    </tr>`).join('');
}

document.getElementById('refresh-overview')?.addEventListener('click', loadOverview);

// ── BOOKS PAGE ────────────────────────────────────────────────────────────────
async function loadBooks() {
  const grid = document.getElementById('books-grid');
  grid.innerHTML = `<div class="spinner-wrap" style="grid-column:1/-1"><div class="spinner"></div></div>`;
  const search = document.getElementById('book-search').value.trim();
  const avail  = document.getElementById('book-avail-filter').value;
  try {
    const data = await booksAPI.getAll(booksPage * LIMIT, LIMIT, search);
    let books = data.books;
    if (avail === 'available') books = books.filter(b => b.available_copies > 0);
    renderBooksGrid(books, data.total);
    renderPagination('books-pagination', booksPage, data.total, LIMIT, (p) => { booksPage = p; loadBooks(); });
  } catch (e) { toast(e.message, 'error'); grid.innerHTML = `<p class="text-muted">${e.message}</p>`; }
}

function renderBooksGrid(books, total) {
  const grid = document.getElementById('books-grid');
  if (!books.length) {
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-icon">📚</div><h3>No books found</h3><p>Try a different search</p></div>`;
    return;
  }
  grid.innerHTML = books.map(b => `
    <div class="book-card">
      <div class="book-card-spine"></div>
      <div class="book-title">${esc(b.title)}</div>
      <div class="book-author">by ${esc(b.author)}</div>
      ${b.isbn ? `<div class="book-isbn">ISBN: ${b.isbn}</div>` : ''}
      ${b.published_year ? `<div class="text-muted" style="font-size:0.78rem">${b.published_year}</div>` : ''}
      <div class="book-meta">
        <span class="badge badge-${b.available_copies > 0 ? 'available' : 'unavailable'}">
          ${b.available_copies > 0 ? 'Available' : 'Unavailable'}
        </span>
        <span class="copies-badge">${b.available_copies}/${b.total_copies} copies</span>
      </div>
      ${b.description ? `<p style="font-size:0.78rem;color:var(--text3);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(b.description)}</p>` : ''}
      <div class="book-actions">
        ${b.available_copies > 0
          ? `<button class="btn btn-sm btn-primary" onclick="window._borrowBook(${b.id}, '${esc(b.title)}')">Borrow</button>`
          : `<button class="btn btn-sm btn-ghost" disabled>Unavailable</button>`
        }
      </div>
    </div>`).join('');
}

const debouncedLoadBooks = debounce(loadBooks, 400);
document.getElementById('book-search')?.addEventListener('input', () => { booksPage = 0; debouncedLoadBooks(); });
document.getElementById('book-avail-filter')?.addEventListener('change', () => { booksPage = 0; loadBooks(); });

// ── MY BORROWS ────────────────────────────────────────────────────────────────
async function loadMyBorrows() {
  const tbody = document.getElementById('borrows-body');
  tbody.innerHTML = `<tr><td colspan="6" class="text-muted" style="text-align:center;padding:20px">Loading...</td></tr>`;
  const status = document.getElementById('borrow-status-filter').value;
  try {
    const data = await borrowAPI.getAll(borrowsPage * LIMIT, LIMIT, status);
    renderBorrowsTable(data.borrows, 'borrows-body', false);
    renderPagination('borrows-pagination', borrowsPage, data.total, LIMIT, (p) => { borrowsPage = p; loadMyBorrows(); });
  } catch (e) { toast(e.message, 'error'); }
}

document.getElementById('borrow-status-filter')?.addEventListener('change', () => { borrowsPage = 0; loadMyBorrows(); });
document.getElementById('refresh-borrows')?.addEventListener('click', loadMyBorrows);

// ── MANAGE BOOKS (ADMIN) ──────────────────────────────────────────────────────
async function loadManage() {
  const tbody = document.getElementById('manage-body');
  tbody.innerHTML = `<tr><td colspan="7" class="text-muted" style="text-align:center;padding:20px">Loading...</td></tr>`;
  const search = document.getElementById('manage-search').value.trim();
  try {
    const data = await booksAPI.getAll(managePage * LIMIT, LIMIT, search);
    renderManageTable(data.books);
    renderPagination('manage-pagination', managePage, data.total, LIMIT, (p) => { managePage = p; loadManage(); });
  } catch (e) { toast(e.message, 'error'); }
}

function renderManageTable(books) {
  const tbody = document.getElementById('manage-body');
  if (!books.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="empty-icon">📚</div><h3>No books</h3></div></td></tr>`;
    return;
  }
  tbody.innerHTML = books.map(b => `
    <tr>
      <td><strong>${esc(b.title)}</strong></td>
      <td>${esc(b.author)}</td>
      <td><code style="font-size:0.75rem">${b.isbn || '—'}</code></td>
      <td>${b.published_year || '—'}</td>
      <td>${b.total_copies}</td>
      <td><span class="badge badge-${b.available_copies > 0 ? 'available' : 'unavailable'}">${b.available_copies}</span></td>
      <td>
        <div class="flex gap-2">
          <button class="btn btn-sm btn-secondary" onclick="window._editBook(${b.id})">Edit</button>
          <button class="btn btn-sm btn-danger" onclick="window._deleteBook(${b.id}, '${esc(b.title)}')">Delete</button>
        </div>
      </td>
    </tr>`).join('');
}

const debouncedLoadManage = debounce(loadManage, 400);
document.getElementById('manage-search')?.addEventListener('input', () => { managePage = 0; debouncedLoadManage(); });

// ── ALL BORROWS (ADMIN) ───────────────────────────────────────────────────────
async function loadAllBorrows() {
  const tbody = document.getElementById('all-borrows-body');
  tbody.innerHTML = `<tr><td colspan="6" class="text-muted" style="text-align:center;padding:20px">Loading...</td></tr>`;
  const status = document.getElementById('all-borrow-filter').value;
  try {
    const data = await borrowAPI.getAll(allBorrowsPage * LIMIT, LIMIT, status);
    renderAllBorrowsTable(data.borrows);
    renderPagination('all-borrows-pagination', allBorrowsPage, data.total, LIMIT, (p) => { allBorrowsPage = p; loadAllBorrows(); });
  } catch (e) { toast(e.message, 'error'); }
}

function renderAllBorrowsTable(borrows) {
  const tbody = document.getElementById('all-borrows-body');
  if (!borrows.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-icon">📭</div><h3>No borrow records</h3></div></td></tr>`;
    return;
  }
  tbody.innerHTML = borrows.map(b => `
    <tr>
      <td><span style="font-weight:600">${b.user?.username || `User #${b.user_id}`}</span><br/><small class="text-muted">${b.user?.email || ''}</small></td>
      <td><strong>${b.book?.title || `Book #${b.book_id}`}</strong></td>
      <td>${fmtDate(b.borrowed_at)}</td>
      <td>${fmtDate(b.due_date)}</td>
      <td><span class="badge badge-${b.status}">${b.status}</span></td>
      <td>
        <div class="flex gap-2">
          ${b.status === 'active' ? `<button class="btn btn-sm btn-teal" onclick="window._adminReturn(${b.id})">Return</button>` : ''}
          <button class="btn btn-sm btn-danger" onclick="window._deleteBorrow(${b.id})">Delete</button>
        </div>
      </td>
    </tr>`).join('');
}

document.getElementById('all-borrow-filter')?.addEventListener('change', () => { allBorrowsPage = 0; loadAllBorrows(); });
document.getElementById('refresh-all-borrows')?.addEventListener('click', loadAllBorrows);

// ── BOOK MODAL ────────────────────────────────────────────────────────────────
document.getElementById('add-book-btn')?.addEventListener('click', () => {
  document.getElementById('book-modal-title').textContent = 'Add New Book';
  document.getElementById('book-id').value = '';
  ['book-title','book-author','book-isbn','book-desc'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('book-year').value = '';
  document.getElementById('book-copies').value = 1;
  openModal('book-modal');
});

document.getElementById('book-save-btn')?.addEventListener('click', async () => {
  const id    = document.getElementById('book-id').value;
  const title = document.getElementById('book-title').value.trim();
  const author= document.getElementById('book-author').value.trim();
  const isbn  = document.getElementById('book-isbn').value.trim();
  const year  = document.getElementById('book-year').value;
  const desc  = document.getElementById('book-desc').value.trim();
  const copies= parseInt(document.getElementById('book-copies').value);
  if (!title || !author) { toast('Title and Author are required', 'warning'); return; }
  const payload = { title, author, total_copies: copies || 1 };
  if (isbn)  payload.isbn = isbn;
  if (year)  payload.published_year = parseInt(year);
  if (desc)  payload.description = desc;
  const btn = document.getElementById('book-save-btn');
  btn.disabled = true; btn.textContent = 'Saving...';
  try {
    if (id) {
      await booksAPI.update(id, payload);
      toast('Book updated successfully', 'success');
    } else {
      await booksAPI.create(payload);
      toast('Book added successfully', 'success');
    }
    closeModal('book-modal');
    loadManage();
  } catch (e) { toast(e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'Save Book'; }
});

// ── MONITORING ────────────────────────────────────────────────────────────────
async function loadMonitoring() {
  try {
    const [m, l] = await Promise.all([dashboardAPI.metrics(), dashboardAPI.logs(20)]);
    document.getElementById('m-total').textContent     = m.total_requests?.toLocaleString() || '0';
    document.getElementById('m-recent-req').textContent = `${m.requests_last_60s || 0} /60s`;
    document.getElementById('m-avg').textContent       = m.response_time?.avg_ms || '0';
    document.getElementById('m-err').textContent       = m.error_rate_percent || '0';
    document.getElementById('m-auth-ok').textContent   = m.auth?.success || '0';
    document.getElementById('m-auth-fail').textContent = `${m.auth?.failure || 0} failures`;

    // Endpoints
    const eps = m.top_endpoints || [];
    const maxC = eps.length ? eps[0].count : 1;
    document.getElementById('m-endpoints').innerHTML = eps.length
      ? eps.map(e => `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:0.8rem">
          <span style="color:var(--text3);width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex-shrink:0">${e.endpoint}</span>
          <div style="flex:1;background:var(--bg3);border-radius:3px;height:6px"><div style="width:${Math.round(e.count/maxC*100)}%;background:var(--gold);height:100%;border-radius:3px"></div></div>
          <span style="font-weight:700;width:28px;text-align:right">${e.count}</span></div>`).join('')
      : '<p class="text-muted">No data yet</p>';

    // Status codes
    const statuses = m.status_breakdown || {};
    const colors = { 2:'var(--green)', 3:'var(--teal)', 4:'var(--amber)', 5:'var(--red)' };
    document.getElementById('m-status').innerHTML = Object.entries(statuses).map(([code, cnt]) =>
      `<span style="display:inline-block;margin:4px;padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:700;background:rgba(255,255,255,0.05);color:${colors[code[0]]||'var(--text)'}">${code}: ${cnt}</span>`
    ).join('') || '<p class="text-muted">No data</p>';

    // Errors table
    const errors = (m.recent_errors || []).slice().reverse();
    document.getElementById('m-errors').innerHTML = errors.length
      ? errors.map(e => `<tr>
          <td style="color:var(--text3);font-size:0.78rem">${e.timestamp}</td>
          <td><code>${e.method}</code></td>
          <td>${e.endpoint}</td>
          <td><span style="color:${e.status_code >= 500 ? 'var(--red)' : 'var(--amber)'};font-weight:700">${e.status_code}</span></td>
        </tr>`).join('')
      : '<tr><td colspan="4" class="text-muted" style="padding:14px;text-align:center">No errors 🎉</td></tr>';

    // Logs
    const logEl = document.getElementById('m-logs');
    const lines = l.lines || [];
    const logColors = { ERROR:'#f43f5e', WARNING:'#fbbf24', CRITICAL:'#ff1744', DEBUG:'#6b6f8a', INFO:'#7dd3fc' };
    logEl.innerHTML = lines.map(line => {
      const level = ['ERROR','WARNING','CRITICAL','DEBUG','INFO'].find(l => line.includes(`| ${l}`)) || 'INFO';
      return `<div style="color:${logColors[level]}">${escHtml(line)}</div>`;
    }).join('');
    logEl.scrollTop = logEl.scrollHeight;
  } catch (e) { /* silently fail */ }
}

// ── Global action handlers ────────────────────────────────────────────────────
window._borrowBook = async (bookId, title) => {
  if (!await confirm(`Borrow "${title}"?`)) return;
  try {
    await borrowAPI.borrow(bookId);
    toast('Book borrowed successfully!', 'success');
    loadBooks();
    loadOverview();
  } catch (e) { toast(e.message, 'error'); }
};

window._returnBook = async (borrowId) => {
  if (!await confirm('Return this book?')) return;
  try {
    await borrowAPI.return_(borrowId);
    toast('Book returned successfully!', 'success');
    loadOverview();
    if (currentPage === 'borrows') loadMyBorrows();
  } catch (e) { toast(e.message, 'error'); }
};

window._adminReturn = async (borrowId) => {
  if (!await confirm('Mark this borrow as returned?')) return;
  try {
    await borrowAPI.return_(borrowId);
    toast('Borrow marked as returned', 'success');
    loadAllBorrows();
  } catch (e) { toast(e.message, 'error'); }
};

window._editBook = async (bookId) => {
  try {
    const b = await booksAPI.getById(bookId);
    document.getElementById('book-modal-title').textContent = 'Edit Book';
    document.getElementById('book-id').value        = b.id;
    document.getElementById('book-title').value     = b.title;
    document.getElementById('book-author').value    = b.author;
    document.getElementById('book-isbn').value      = b.isbn || '';
    document.getElementById('book-year').value      = b.published_year || '';
    document.getElementById('book-desc').value      = b.description || '';
    document.getElementById('book-copies').value    = b.total_copies;
    openModal('book-modal');
  } catch (e) { toast(e.message, 'error'); }
};

window._deleteBook = async (bookId, title) => {
  if (!await confirm(`Permanently delete "${title}"? This cannot be undone.`)) return;
  try {
    await booksAPI.delete(bookId);
    toast('Book deleted', 'success');
    loadManage();
  } catch (e) { toast(e.message, 'error'); }
};

window._deleteBorrow = async (borrowId) => {
  if (!await confirm('Permanently delete this borrow record?')) return;
  try {
    await borrowAPI.delete(borrowId);
    toast('Borrow record deleted', 'success');
    loadAllBorrows();
  } catch (e) { toast(e.message, 'error'); }
};

// ── Borrows table helper ──────────────────────────────────────────────────────
function renderBorrowsTable(borrows, tbodyId, isAdmin) {
  const tbody = document.getElementById(tbodyId);
  if (!borrows.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-icon">📭</div><h3>No borrow records</h3></div></td></tr>`;
    return;
  }
  tbody.innerHTML = borrows.map(b => `
    <tr>
      <td><strong>${b.book?.title || `Book #${b.book_id}`}</strong></td>
      <td>${fmtDate(b.borrowed_at)}</td>
      <td>${fmtDate(b.due_date)}</td>
      <td>${fmtDate(b.returned_at)}</td>
      <td><span class="badge badge-${b.status}">${b.status}</span></td>
      <td>${b.status === 'active' ? `<button class="btn btn-sm btn-teal" onclick="window._returnBook(${b.id})">Return</button>` : '—'}</td>
    </tr>`).join('');
}

// ── Pagination ────────────────────────────────────────────────────────────────
function renderPagination(containerId, currentP, total, limit, onPageChange) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const totalPages = Math.ceil(total / limit);
  if (totalPages <= 1) { container.innerHTML = ''; return; }
  let html = `<button ${currentP === 0 ? 'disabled' : ''} onclick="(${onPageChange.toString()})(${currentP - 1})">‹ Prev</button>`;
  for (let i = 0; i < Math.min(totalPages, 7); i++) {
    html += `<button class="${i === currentP ? 'active' : ''}" onclick="(${onPageChange.toString()})(${i})">${i + 1}</button>`;
  }
  html += `<button ${currentP >= totalPages - 1 ? 'disabled' : ''} onclick="(${onPageChange.toString()})(${currentP + 1})">Next ›</button>`;
  container.innerHTML = html;
}

// ── Escape HTML ───────────────────────────────────────────────────────────────
function esc(s) { return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escHtml(s) { return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
