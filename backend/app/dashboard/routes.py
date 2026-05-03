"""
app/dashboard/routes.py
────────────────────────
Monitoring dashboard endpoints.

GET /dashboard        → HTML dashboard UI
GET /dashboard/metrics → JSON metrics (for API consumers)
GET /dashboard/logs   → last N lines from app.log
"""

import os
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from app.system.metrics import metrics
from app.system.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

LOG_FILE = Path("logs/app.log")


# ── JSON metrics endpoint ─────────────────────────────────────────────────────

@router.get("/metrics", response_class=JSONResponse, summary="Live metrics (JSON)")
async def get_metrics():
    """Returns all collected metrics as JSON."""
    return metrics.summary()


# ── Log tail endpoint ─────────────────────────────────────────────────────────

@router.get("/logs", response_class=JSONResponse, summary="Recent log lines")
async def get_logs(lines: int = Query(50, ge=1, le=500)):
    """Returns the last N lines from the application log file."""
    if not LOG_FILE.exists():
        return {"lines": [], "message": "Log file not found yet."}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        tail = [l.rstrip() for l in all_lines[-lines:]]
        return {"total_lines": len(all_lines), "showing": len(tail), "lines": tail}
    except Exception as e:
        logger.error("Error reading log file: %s", e)
        return {"lines": [], "error": str(e)}


# ── HTML Dashboard ────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Renders the monitoring dashboard HTML page."""
    html = _build_dashboard_html()
    return HTMLResponse(content=html)


# ── HTML builder ─────────────────────────────────────────────────────────────

def _build_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Library API — Monitoring Dashboard</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --border: #2a2d3e;
    --accent: #6c63ff; --accent2: #00d4aa; --danger: #ff4757;
    --warn: #ffa502; --text: #e2e8f0; --muted: #94a3b8;
    --success: #2ed573;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }

  header {
    background: linear-gradient(135deg, #1a1d27 0%, #12151f 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 32px;
    display: flex; align-items: center; justify-content: space-between;
  }
  header h1 { font-size: 1.4rem; font-weight: 700; }
  header h1 span { color: var(--accent); }
  .status-badge {
    display: flex; align-items: center; gap: 8px;
    background: rgba(46,213,115,0.1); border: 1px solid var(--success);
    color: var(--success); padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 600;
  }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--success); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(1.3)} }

  main { padding: 28px 32px; max-width: 1400px; margin: 0 auto; }

  .last-updated { color: var(--muted); font-size: 0.78rem; margin-bottom: 20px; }

  /* Stat cards */
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; position: relative; overflow: hidden;
  }
  .stat-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background: var(--accent); }
  .stat-card.danger::before { background: var(--danger); }
  .stat-card.success::before { background: var(--success); }
  .stat-card.warn::before { background: var(--warn); }
  .stat-card.accent2::before { background: var(--accent2); }
  .stat-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 8px; }
  .stat-value { font-size: 2rem; font-weight: 800; line-height: 1; }
  .stat-sub { font-size: 0.78rem; color: var(--muted); margin-top: 6px; }

  /* Sections */
  .section-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
  @media (max-width: 900px) { .section-grid { grid-template-columns: 1fr; } }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px;
  }
  .card h2 { font-size: 0.9rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-bottom: 16px; }

  /* Bar chart */
  .bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; font-size: 0.82rem; }
  .bar-label { width: 160px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--muted); flex-shrink: 0; }
  .bar-track { flex: 1; background: rgba(255,255,255,0.05); border-radius: 4px; height: 8px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; background: var(--accent); transition: width 0.6s ease; }
  .bar-count { width: 36px; text-align: right; font-weight: 600; color: var(--text); flex-shrink: 0; }

  /* Status doughnut-style pills */
  .status-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .status-pill {
    padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 700;
    display: flex; align-items: center; gap: 6px;
  }
  .s2xx { background: rgba(46,213,115,.15); color: var(--success); border: 1px solid var(--success); }
  .s3xx { background: rgba(0,212,170,.15); color: var(--accent2); border: 1px solid var(--accent2); }
  .s4xx { background: rgba(255,165,2,.15);  color: var(--warn);    border: 1px solid var(--warn); }
  .s5xx { background: rgba(255,71,87,.15);  color: var(--danger);  border: 1px solid var(--danger); }

  /* Auth card */
  .auth-row { display: flex; gap: 16px; }
  .auth-box { flex: 1; border-radius: 10px; padding: 16px; text-align: center; }
  .auth-box.ok  { background: rgba(46,213,115,.1);  border: 1px solid var(--success); }
  .auth-box.bad { background: rgba(255,71,87,.1);   border: 1px solid var(--danger); }
  .auth-box .num { font-size: 2.2rem; font-weight: 800; }
  .auth-box .lbl { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }

  /* Errors table */
  .error-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  .error-table th { text-align: left; padding: 8px 10px; color: var(--muted); border-bottom: 1px solid var(--border); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; }
  .error-table td { padding: 9px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .error-table tr:last-child td { border-bottom: none; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 700; }
  .b4xx { background: rgba(255,165,2,.2); color: var(--warn); }
  .b5xx { background: rgba(255,71,87,.2); color: var(--danger); }

  /* Logs */
  .log-box {
    background: #0a0c14; border: 1px solid var(--border); border-radius: 8px;
    padding: 14px; font-family: 'Courier New', monospace; font-size: 0.75rem;
    max-height: 320px; overflow-y: auto; line-height: 1.6;
  }
  .log-line { white-space: pre-wrap; word-break: break-all; }
  .log-line.ERROR   { color: var(--danger); }
  .log-line.WARNING { color: var(--warn); }
  .log-line.INFO    { color: #7dd3fc; }
  .log-line.DEBUG   { color: var(--muted); }
  .log-line.CRITICAL { color: #ff1744; font-weight: bold; }

  /* CRUD */
  .crud-grid { display: flex; flex-wrap: wrap; gap: 10px; }
  .crud-chip {
    background: rgba(108,99,255,.1); border: 1px solid rgba(108,99,255,.3);
    border-radius: 8px; padding: 8px 14px; font-size: 0.82rem;
  }
  .crud-chip span { color: var(--accent); font-weight: 700; }

  .refresh-btn {
    background: var(--accent); color: white; border: none; border-radius: 8px;
    padding: 8px 18px; cursor: pointer; font-size: 0.82rem; font-weight: 600;
    transition: opacity .2s;
  }
  .refresh-btn:hover { opacity: 0.85; }

  .full-width { grid-column: 1 / -1; }
  .empty { color: var(--muted); font-size: 0.82rem; font-style: italic; }

  .uptime-badge {
    display: inline-block; background: rgba(108,99,255,.1); border: 1px solid rgba(108,99,255,.3);
    color: var(--accent); padding: 3px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: 600;
  }
</style>
</head>
<body>

<header>
  <h1>📚 <span>Library API</span> — Monitoring Dashboard</h1>
  <div style="display:flex;gap:12px;align-items:center">
    <button class="refresh-btn" onclick="loadAll()">⟳ Refresh</button>
    <div class="status-badge"><div class="pulse"></div> LIVE</div>
  </div>
</header>

<main>
  <div class="last-updated">Last updated: <span id="last-updated">—</span> &nbsp;|&nbsp; Auto-refresh every <b>10s</b> &nbsp;|&nbsp; Uptime: <span id="uptime" class="uptime-badge">—</span></div>

  <!-- Stat cards -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Requests</div>
      <div class="stat-value" id="total-req">—</div>
      <div class="stat-sub" id="recent-req">— in last 60s</div>
    </div>
    <div class="stat-card accent2">
      <div class="stat-label">Avg Response Time</div>
      <div class="stat-value" id="avg-ms">—</div>
      <div class="stat-sub" id="recent-ms">recent avg: —</div>
    </div>
    <div class="stat-card warn">
      <div class="stat-label">Error Rate (60s)</div>
      <div class="stat-value" id="error-rate">—</div>
      <div class="stat-sub">% of recent requests</div>
    </div>
    <div class="stat-card success">
      <div class="stat-label">Auth Success</div>
      <div class="stat-value" id="auth-ok">—</div>
      <div class="stat-sub" id="auth-fail-sub">— failures</div>
    </div>
    <div class="stat-card danger">
      <div class="stat-label">Max Response Time</div>
      <div class="stat-value" id="max-ms">—</div>
      <div class="stat-sub" id="min-ms">min: —</div>
    </div>
  </div>

  <!-- Row 2: endpoints + status -->
  <div class="section-grid">
    <div class="card">
      <h2>🔥 Top Endpoints</h2>
      <div id="endpoints-chart"><p class="empty">No data yet</p></div>
    </div>
    <div class="card">
      <h2>📊 Status Code Breakdown</h2>
      <div class="status-grid" id="status-pills"><p class="empty">No data yet</p></div>
      <br/>
      <h2 style="margin-top:12px">⚡ HTTP Methods</h2>
      <div class="status-grid" id="method-pills"></div>
    </div>
  </div>

  <!-- Row 3: auth + crud -->
  <div class="section-grid">
    <div class="card">
      <h2>🔐 Authentication Events</h2>
      <div class="auth-row" id="auth-row">
        <div class="auth-box ok"><div class="num" id="auth-success-n">—</div><div class="lbl">Successful Logins</div></div>
        <div class="auth-box bad"><div class="num" id="auth-failure-n">—</div><div class="lbl">Failed Attempts</div></div>
      </div>
    </div>
    <div class="card">
      <h2>🗄️ CRUD Operations</h2>
      <div class="crud-grid" id="crud-grid"><p class="empty">No operations yet</p></div>
    </div>
  </div>

  <!-- Row 4: recent errors (full width) -->
  <div class="card" style="margin-bottom:24px">
    <h2>🚨 Recent Errors</h2>
    <div id="errors-wrap">
      <table class="error-table">
        <thead><tr><th>Time</th><th>Method</th><th>Endpoint</th><th>Status</th></tr></thead>
        <tbody id="errors-body"><tr><td colspan="4" class="empty" style="padding:12px">No errors recorded 🎉</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- Row 5: live logs (full width) -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h2 style="margin:0">📋 Application Logs <span style="font-size:0.7rem;color:var(--muted)">(last 50 lines)</span></h2>
      <label style="font-size:0.78rem;color:var(--muted)">
        <input type="checkbox" id="auto-scroll" checked/> Auto-scroll
      </label>
    </div>
    <div class="log-box" id="log-box"><span class="empty">Loading logs...</span></div>
  </div>
</main>

<script>
const API = '';

async function fetchMetrics() {
  try {
    const r = await fetch(API + '/dashboard/metrics');
    return await r.json();
  } catch(e) { return null; }
}

async function fetchLogs() {
  try {
    const r = await fetch(API + '/dashboard/logs?lines=50');
    return await r.json();
  } catch(e) { return null; }
}

function colorForStatus(code) {
  if (code < 300) return 's2xx';
  if (code < 400) return 's3xx';
  if (code < 500) return 's4xx';
  return 's5xx';
}

function colorForBadge(code) {
  return code < 500 ? 'b4xx' : 'b5xx';
}

function logClass(line) {
  if (line.includes('| ERROR') || line.includes('ERROR')) return 'ERROR';
  if (line.includes('| WARNING') || line.includes('WARNING')) return 'WARNING';
  if (line.includes('| CRITICAL') || line.includes('CRITICAL')) return 'CRITICAL';
  if (line.includes('| DEBUG') || line.includes('DEBUG')) return 'DEBUG';
  return 'INFO';
}

function renderMetrics(d) {
  if (!d) return;
  document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
  document.getElementById('uptime').textContent = d.uptime || '—';

  // Stat cards
  document.getElementById('total-req').textContent = d.total_requests.toLocaleString();
  document.getElementById('recent-req').textContent = (d.requests_last_60s || 0) + ' in last 60s';
  document.getElementById('avg-ms').textContent = (d.response_time.avg_ms || 0) + ' ms';
  document.getElementById('recent-ms').textContent = 'recent avg: ' + (d.response_time.recent_avg_ms || 0) + ' ms';
  document.getElementById('max-ms').textContent = (d.response_time.max_ms || 0) + ' ms';
  document.getElementById('min-ms').textContent = 'min: ' + (d.response_time.min_ms || 0) + ' ms';

  const errRate = d.error_rate_percent || 0;
  const errEl = document.getElementById('error-rate');
  errEl.textContent = errRate + '%';
  errEl.style.color = errRate > 10 ? 'var(--danger)' : errRate > 2 ? 'var(--warn)' : 'var(--success)';

  document.getElementById('auth-ok').textContent = d.auth.success;
  document.getElementById('auth-fail-sub').textContent = (d.auth.failure || 0) + ' failures';
  document.getElementById('auth-success-n').textContent = d.auth.success;
  document.getElementById('auth-failure-n').textContent = d.auth.failure;

  // Top endpoints bar chart
  const eps = d.top_endpoints || [];
  const maxCount = eps.length ? eps[0].count : 1;
  const epEl = document.getElementById('endpoints-chart');
  if (eps.length === 0) { epEl.innerHTML = '<p class="empty">No requests yet</p>'; }
  else {
    epEl.innerHTML = eps.map(ep => {
      const pct = Math.round((ep.count / maxCount) * 100);
      return `<div class="bar-row">
        <div class="bar-label" title="${ep.endpoint}">${ep.endpoint}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-count">${ep.count}</div>
      </div>`;
    }).join('');
  }

  // Status pills
  const statuses = d.status_breakdown || {};
  const pillEl = document.getElementById('status-pills');
  const pills = Object.entries(statuses).map(([code, cnt]) =>
    `<div class="status-pill ${colorForStatus(parseInt(code))}">${code}<strong>${cnt.toLocaleString()}</strong></div>`
  );
  pillEl.innerHTML = pills.length ? pills.join('') : '<p class="empty">No requests yet</p>';

  // Method pills
  const methods = d.method_counts || {};
  const methodColors = {GET:'s2xx', POST:'s3xx', PUT:'s4xx', DELETE:'s5xx', PATCH:'s3xx'};
  document.getElementById('method-pills').innerHTML = Object.entries(methods).map(([m, c]) =>
    `<div class="status-pill ${methodColors[m]||'s2xx'}">${m} <strong>${c}</strong></div>`
  ).join('');

  // CRUD
  const crud = d.crud_operations || {};
  const crudEl = document.getElementById('crud-grid');
  const chips = Object.entries(crud).map(([k,v]) => {
    const [op, res] = k.split(':');
    return `<div class="crud-chip"><span>${op}</span> ${res||''} × ${v}</div>`;
  });
  crudEl.innerHTML = chips.length ? chips.join('') : '<p class="empty">No CRUD operations yet</p>';

  // Recent errors table
  const errors = (d.recent_errors || []).slice().reverse();
  const tbody = document.getElementById('errors-body');
  if (errors.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty" style="padding:12px">No errors recorded 🎉</td></tr>';
  } else {
    tbody.innerHTML = errors.map(e => `
      <tr>
        <td style="color:var(--muted)">${e.timestamp}</td>
        <td><code>${e.method}</code></td>
        <td style="color:var(--text)">${e.endpoint}</td>
        <td><span class="badge ${colorForBadge(e.status_code)}">${e.status_code}</span></td>
      </tr>`).join('');
  }
}

function renderLogs(data) {
  if (!data) return;
  const box = document.getElementById('log-box');
  const lines = data.lines || [];
  if (lines.length === 0) { box.innerHTML = '<span class="empty">No logs yet</span>'; return; }
  box.innerHTML = lines.map(l =>
    `<div class="log-line ${logClass(l)}">${escapeHtml(l)}</div>`
  ).join('');
  if (document.getElementById('auto-scroll').checked) {
    box.scrollTop = box.scrollHeight;
  }
}

function escapeHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function loadAll() {
  const [m, l] = await Promise.all([fetchMetrics(), fetchLogs()]);
  renderMetrics(m);
  renderLogs(l);
}

loadAll();
setInterval(loadAll, 10000);
</script>
</body>
</html>"""
