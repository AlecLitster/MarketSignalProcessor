'use strict';

const POLL_MS = 60_000;
let _pollTimer   = null;
let _nextRefresh = null;

// ── Formatting helpers ───────────────────────────────────────────────────────

function signalBadge(sig) {
  if (!sig || sig === 'N/A' || sig === '—') {
    return '<span class="badge badge-NA">N/A</span>';
  }
  const s = sig.toUpperCase().replace(/\s+/g, '_');
  if (s === 'BUY'  || s === 'STRONG_BUY')  return `<span class="badge badge-BUY">${sig}</span>`;
  if (s === 'SELL' || s === 'STRONG_SELL') return `<span class="badge badge-SELL">${sig}</span>`;
  if (s === 'OVERBOUGHT')                   return `<span class="badge badge-OVERBOUGHT">OB</span>`;
  if (s === 'OVERSOLD')                     return `<span class="badge badge-OVERSOLD">OS</span>`;
  if (s === 'WEAK_TREND')                   return `<span class="badge badge-HOLD">WEAK</span>`;
  return `<span class="badge badge-HOLD">${sig}</span>`;
}

function swingBadge(label) {
  if (!label || label === '—') return '<span class="muted">—</span>';
  const cls  = label.replace(/\s+/g, '_').toUpperCase();
  const text = label.replace(/_/g, ' ');
  return `<span class="swing-badge swing-${cls}">${text}</span>`;
}

function scoreBar(val) {
  if (val === null || val === undefined || val === '') return '<span class="muted">—</span>';
  const n = parseFloat(val);
  if (isNaN(n)) return `<span class="muted">${val}</span>`;
  const clamped = Math.min(Math.max(n, -1), 1);
  const pct     = Math.round(((clamped + 1) / 2) * 100);
  const color   = n > 0.05 ? 'var(--buy)' : n < -0.05 ? 'var(--sell)' : 'var(--hold)';
  const numCls  = n > 0.05 ? 'num-buy'   : n < -0.05 ? 'num-sell'   : 'num-hold';
  const sign    = n >= 0 ? '+' : '';
  return `<div class="score-cell">
    <div class="score-bar-wrap"><div class="score-bar" style="width:${pct}%;background:${color}"></div></div>
    <span class="score-val ${numCls}">${sign}${n.toFixed(3)}</span>
  </div>`;
}

function fmtPrice(val) {
  if (val === null || val === undefined || val === '') return '<span class="muted">—</span>';
  const n = parseFloat(val);
  return isNaN(n) ? '<span class="muted">—</span>' : `$${n.toFixed(2)}`;
}

function fmtTime(iso) {
  if (!iso) return '<span class="muted">—</span>';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function rowCls(signal, swingLabel) {
  const parts = [];
  if (signal) {
    const s = signal.toUpperCase().replace(/\s+/g, '_');
    if (s === 'BUY'  || s === 'STRONG_BUY')  parts.push('row-buy');
    if (s === 'SELL' || s === 'STRONG_SELL') parts.push('row-sell');
  }
  if (swingLabel) {
    parts.push(`has-swing-${swingLabel.replace(/\s+/g, '_').toUpperCase()}`);
  }
  return parts.join(' ');
}

// ── Network ──────────────────────────────────────────────────────────────────

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

// ── Poll loop ────────────────────────────────────────────────────────────────

async function refresh() {
  setDot('loading');
  try {
    const [signals, status] = await Promise.all([
      fetchJson('/api/signals'),
      fetchJson('/api/status'),
    ]);
    renderSummary(signals);
    renderSwings(signals);
    renderStatus(status);
    document.getElementById('last-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
    setDot('ok');
  } catch (err) {
    console.error(err);
    document.getElementById('last-updated').textContent = 'Error — retrying…';
    setDot('error');
  }
  scheduleNext();
}

function scheduleNext() {
  if (_pollTimer) clearTimeout(_pollTimer);
  _nextRefresh = Date.now() + POLL_MS;
  _pollTimer   = setTimeout(refresh, POLL_MS);
  tickCountdown();
}

function tickCountdown() {
  const el   = document.getElementById('next-refresh');
  const secs = Math.max(0, Math.round((_nextRefresh - Date.now()) / 1000));
  if (el) el.textContent = `Next in ${secs}s`;
  if (secs > 0) setTimeout(tickCountdown, 1000);
}

function setDot(state) {
  const d = document.getElementById('status-dot');
  if (d) d.className = 'status-dot ' + state;
}

// ── Summary table ────────────────────────────────────────────────────────────

function renderSummary(signals) {
  const tbody = document.getElementById('summary-body');
  if (!signals || signals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="13" class="loading">No data yet — waiting for first cycle.</td></tr>';
    return;
  }

  tbody.innerHTML = signals.map(r => {
    const rc = rowCls(r.consensus_signal, r.swing_label);
    return `<tr class="ticker-row ${rc}" data-ticker="${r.ticker}">
      <td class="ticker-cell">${r.ticker}</td>
      <td class="price-cell">${fmtPrice(r.price)}</td>
      <td>${signalBadge(r.tv_signal)}</td>
      <td>${scoreBar(r.tv_score)}</td>
      <td>${signalBadge(r.yf_signal)}</td>
      <td>${scoreBar(r.yf_score)}</td>
      <td>${signalBadge(r.ai_signal)}</td>
      <td class="muted">${r.ai_confidence || '—'}</td>
      <td class="ai-target">${r.ai_price_target ? '$' + parseFloat(r.ai_price_target).toFixed(2) : '<span class="muted">—</span>'}</td>
      <td class="consensus-col">${signalBadge(r.consensus_signal)}</td>
      <td>${scoreBar(r.consensus_score)}</td>
      <td>${swingBadge(r.swing_label)}</td>
      <td class="muted time-col">${fmtTime(r.timestamp)}</td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('.ticker-row').forEach(tr =>
    tr.addEventListener('click', () => loadDetail(tr.dataset.ticker))
  );
}

// ── Swing alerts ─────────────────────────────────────────────────────────────

function renderSwings(signals) {
  const section = document.getElementById('swing-section');
  const box     = document.getElementById('swing-alerts');
  const swings  = (signals || []).filter(s => s.swing_label);

  if (!swings.length) { section.style.display = 'none'; return; }
  section.style.display = '';

  box.innerHTML = swings.map(s => {
    const key = (s.swing_label || '').replace(/\s+/g, '_').toUpperCase();
    const borderColor = key.includes('STRONG') ? 'var(--swing-strong)'
                      : key.includes('WEAK')   ? 'var(--swing-weak)'
                      : key.includes('SCORE')  ? 'var(--swing-score)'
                      : 'var(--swing-change)';
    const arrow    = s.consensus_signal === 'BUY' ? '▲' : s.consensus_signal === 'SELL' ? '▼' : '◆';
    const arrowCls = s.consensus_signal === 'BUY' ? 'num-buy' : s.consensus_signal === 'SELL' ? 'num-sell' : '';
    const score    = parseFloat(s.consensus_score);
    return `<div class="swing-alert-card" style="border-left-color:${borderColor}">
      <span class="alert-ticker">${s.ticker}</span>
      <span class="alert-arrow ${arrowCls}">${arrow}</span>
      <div>
        <div style="display:flex;align-items:center;gap:8px">${swingBadge(s.swing_label)} ${signalBadge(s.consensus_signal)}</div>
        <div class="alert-detail">Score: ${score >= 0 ? '+' : ''}${score.toFixed(3)}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Detail panel ─────────────────────────────────────────────────────────────

async function loadDetail(ticker) {
  const section = document.getElementById('detail-section');
  section.style.display = '';
  document.getElementById('detail-ticker').textContent = ticker;
  document.getElementById('history-body').innerHTML =
    '<tr><td colspan="8" class="loading">Loading…</td></tr>';

  try {
    const history = await fetchJson(`/api/history/${ticker}`);
    renderHistory(history.slice().reverse());
  } catch {
    document.getElementById('history-body').innerHTML =
      '<tr><td colspan="8" class="loading">Failed to load history.</td></tr>';
  }

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderHistory(history) {
  const tbody = document.getElementById('history-body');
  if (!history || history.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="loading">No history on record.</td></tr>';
    return;
  }
  tbody.innerHTML = history.map(e => {
    const tv  = e.tradingview ? e.tradingview.signal : null;
    const yf  = e.yfinance    ? e.yfinance.signal    : null;
    const ai  = e.ai          ? e.ai.signal          : null;
    const sw  = e.swing_event ? e.swing_event.label  : null;
    const price = (e.tradingview && e.tradingview.price != null) ? e.tradingview.price
                : (e.yfinance   && e.yfinance.price   != null)   ? e.yfinance.price
                : null;
    const rc = rowCls(e.consensus_signal, sw);
    return `<tr class="${rc}">
      <td class="muted time-col">${fmtTime(e.timestamp)}</td>
      <td class="consensus-col">${signalBadge(e.consensus_signal)}</td>
      <td>${scoreBar(e.consensus_score)}</td>
      <td>${signalBadge(tv)}</td>
      <td>${signalBadge(yf)}</td>
      <td>${signalBadge(ai)}</td>
      <td class="price-cell">${fmtPrice(price)}</td>
      <td>${swingBadge(sw)}</td>
    </tr>`;
  }).join('');
}

function closeDetail() {
  document.getElementById('detail-section').style.display = 'none';
}

// ── Service status card ───────────────────────────────────────────────────────

function renderStatus(status) {
  const grid = document.getElementById('status-grid');
  const items = [
    { label: 'State',        value: status.status       || '—',  cls: status.status === 'running' ? 'on' : 'off' },
    { label: 'Tickers',      value: status.ticker_count ?? '—',  cls: '' },
    { label: 'Last Signals', value: status.signal_count ?? '—',  cls: '' },
    { label: 'Started',      value: status.start_time    || '—', cls: '' },
  ];
  grid.innerHTML = items.map(i =>
    `<div class="status-item">
       <div class="label">${i.label}</div>
       <div class="value ${i.cls}">${i.value}</div>
     </div>`
  ).join('');
}

// ── Footer clock ──────────────────────────────────────────────────────────────

function tickClock() {
  const el = document.getElementById('footer-time');
  if (el) el.textContent = new Date().toLocaleString();
  setTimeout(tickClock, 1000);
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  tickClock();
  refresh();
});
