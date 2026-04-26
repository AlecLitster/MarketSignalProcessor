'use strict';

const POLL_MS = 60_000;
let _pollTimer   = null;
let _nextRefresh = null;

// ── Formatting helpers ───────────────────────────────────────────────────────

function signalCls(sig) {
  if (!sig || sig === 'N/A') return '';
  const s = sig.toUpperCase();
  if (s === 'BUY'  || s === 'STRONG BUY')  return 'buy';
  if (s === 'SELL' || s === 'STRONG SELL') return 'sell';
  return 'hold';
}

function swingCls(label) {
  if (!label || label === '—') return '';
  if (label.includes('STRONG')) return 'swing-strong';
  if (label.includes('WEAK'))   return 'swing-weak';
  return 'swing-score';
}

function fmt(val, dp = 4) {
  if (val === null || val === undefined || val === '') return '—';
  const n = parseFloat(val);
  return isNaN(n) ? String(val) : (n >= 0 ? '+' : '') + n.toFixed(dp);
}

function fmtPrice(val) {
  if (val === null || val === undefined || val === '') return '—';
  const n = parseFloat(val);
  return isNaN(n) ? '—' : '$' + n.toFixed(2);
}

function fmtTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
    tbody.innerHTML = '<tr><td colspan="17" class="loading">No data yet — waiting for first cycle.</td></tr>';
    return;
  }

  tbody.innerHTML = signals.map(r => {
    const swing = r.swing_label || '';
    return `<tr class="ticker-row" data-ticker="${r.ticker}">
      <td class="ticker-cell">${r.ticker}</td>
      <td>${fmtPrice(r.price)}</td>
      <td class="${signalCls(r.tv_signal)}">${r.tv_signal || '—'}</td>
      <td>${fmt(r.tv_score)}</td>
      <td class="${signalCls(r.bc_signal)}">${r.bc_signal || '—'}</td>
      <td>${fmt(r.bc_score)}</td>
      <td class="${signalCls(r.ts_signal)}">${r.ts_signal || '—'}</td>
      <td>${r.ts_strength || '—'}</td>
      <td class="${signalCls(r.yf_signal)}">${r.yf_signal || '—'}</td>
      <td>${fmt(r.yf_score)}</td>
      <td class="${signalCls(r.ai_signal)}">${r.ai_signal || '—'}</td>
      <td>${r.ai_confidence || '—'}</td>
      <td>${fmtPrice(r.ai_price_target)}</td>
      <td class="${signalCls(r.consensus_signal)}">${r.consensus_signal || '—'}</td>
      <td>${fmt(r.consensus_score)}</td>
      <td class="${swingCls(swing)}">${swing || '—'}</td>
      <td>${fmtTime(r.timestamp)}</td>
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

  box.innerHTML = swings.map(s => `
    <div class="swing-card ${swingCls(s.swing_label)}">
      <span class="swing-ticker">${s.ticker}</span>
      <span class="swing-label">${s.swing_label}</span>
      <span class="${signalCls(s.consensus_signal)}">${s.consensus_signal}</span>
      <span class="swing-score">${fmt(s.consensus_score)}</span>
    </div>`).join('');
}

// ── Detail panel ─────────────────────────────────────────────────────────────

async function loadDetail(ticker) {
  const section = document.getElementById('detail-section');
  section.style.display = '';
  document.getElementById('detail-ticker').textContent = ticker;
  document.getElementById('history-body').innerHTML =
    '<tr><td colspan="10" class="loading">Loading…</td></tr>';

  try {
    const history = await fetchJson(`/api/history/${ticker}`);
    renderHistory(history.slice().reverse());
  } catch {
    document.getElementById('history-body').innerHTML =
      '<tr><td colspan="10" class="loading">Failed to load history.</td></tr>';
  }

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderHistory(history) {
  const tbody = document.getElementById('history-body');
  if (!history || history.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="loading">No history on record.</td></tr>';
    return;
  }
  tbody.innerHTML = history.map(e => {
    const tv    = e.tradingview  ? e.tradingview.signal  : '—';
    const bc    = e.barchart     ? e.barchart.signal     : '—';
    const ts    = e.trendspotter ? e.trendspotter.signal : '—';
    const yf    = e.yfinance     ? e.yfinance.signal     : '—';
    const ai    = e.ai           ? e.ai.signal           : '—';
    const sw    = e.swing_event  ? e.swing_event.label   : '—';
    const price = (e.tradingview && e.tradingview.price != null)
                ? e.tradingview.price
                : (e.barchart && e.barchart.price != null ? e.barchart.price
                : (e.yfinance && e.yfinance.price != null ? e.yfinance.price : null));
    return `<tr>
      <td>${fmtTime(e.timestamp)}</td>
      <td class="${signalCls(e.consensus_signal)}">${e.consensus_signal}</td>
      <td>${fmt(e.consensus_score)}</td>
      <td class="${signalCls(tv)}">${tv}</td>
      <td class="${signalCls(bc)}">${bc}</td>
      <td class="${signalCls(ts)}">${ts}</td>
      <td class="${signalCls(yf)}">${yf}</td>
      <td class="${signalCls(ai)}">${ai}</td>
      <td>${fmtPrice(price)}</td>
      <td class="${swingCls(sw)}">${sw}</td>
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
    { label: 'State',        value: status.status      || '—' },
    { label: 'Tickers',      value: status.ticker_count ?? '—' },
    { label: 'Last signals', value: status.signal_count ?? '—' },
    { label: 'Started',      value: status.start_time   || '—' },
  ];
  grid.innerHTML = items.map(i =>
    `<div class="status-item">
       <span class="status-label">${i.label}</span>
       <span class="status-value">${i.value}</span>
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
