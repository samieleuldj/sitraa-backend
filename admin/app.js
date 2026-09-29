const API = window.location.origin;
const TOKEN_KEY = 'veloradz_admin_token';
const API_TIMEOUT_MS = 25000;

const state = {
  token: localStorage.getItem(TOKEN_KEY) || '',
  metrics: null,
  orders: [],
  deliveries: null,
  statuses: [],
  products: [],
  selectedOrderId: null,
  currentTab: 'overview',
  rangePreset: '7',
  dateRange: { from: '', to: '' },
  loading: false,
  orderAlerts: {
    enabled: localStorage.getItem('veloradz_order_alerts') !== 'off',
    lastOrderDbId: Number(localStorage.getItem('veloradz_last_order_id') || 0),
    initialized: false,
    pollTimer: null,
    audioReady: false,
  },
};

const $ = (id) => document.getElementById(id);

const USD_TO_DZD = 250.50;

function resolveAdSpendDzd() {
  const usd = Number($('adAmountUsd')?.value || 0);
  const dzd = Number($('adAmount')?.value || 0);
  if (usd > 0) return Math.round(usd * USD_TO_DZD);
  return dzd;
}
function money(v) { return `${Number(v || 0).toLocaleString('fr-DZ')} دج`; }
function pct(v) { return `${Number(v || 0).toFixed(2)}%`; }
function signedMoney(v) {
  const n = Number(v || 0);
  return `${n >= 0 ? '+' : ''}${money(n)}`;
}
function fmtDate(v) {
  if (!v) return '—';
  return new Date(v).toLocaleString('ar-DZ', { timeZone: 'Africa/Algiers' });
}

function statusClass(status) {
  const s = String(status || '').trim();
  const lower = s.toLowerCase();
  if (lower.includes('deliver') || s.includes('تسليم') || s.includes('Livré')) return 'delivered';
  if (lower.includes('return') || s.includes('مرتج') || lower.includes('cancel') || s.includes('ملغ')) return 'returned';
  if (lower.includes('ship') || s.includes('شحن') || lower.includes('expédi')) return 'shipped';
  if (lower.includes('confirm') || s.includes('مؤك')) return 'confirmed';
  if (lower.includes('pending') || s.includes('انتظار')) return 'pending';
  return 'pending';
}

function setLoading(on) {
  state.loading = on;
  const el = $('globalLoading');
  if (el) el.classList.toggle('hidden', !on);
}

function showError(msg) {
  const el = $('globalError');
  if (!el) return;
  if (!msg) {
    el.classList.add('hidden');
    el.textContent = '';
    return;
  }
  el.textContent = msg;
  el.classList.remove('hidden');
}

const ALGIERS_TZ = 'Africa/Algiers';

function formatAlgiersDate(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: ALGIERS_TZ }).format(date);
}

function shiftIsoDate(isoDate, days) {
  const [year, month, day] = isoDate.split('-').map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return shifted.toISOString().slice(0, 10);
}

function setRangeDays(days) {
  const today = formatAlgiersDate(new Date());
  if (days === 0) {
    $('dateFrom').value = today;
    $('dateTo').value = today;
    return { from: today, to: today };
  }
  const from = shiftIsoDate(today, -(days - 1));
  $('dateFrom').value = from;
  $('dateTo').value = today;
  return { from, to: today };
}

function setActiveDateRange(from, to, preset) {
  state.dateRange = { from, to };
  state.rangePreset = preset;
  if ($('dateFrom')) $('dateFrom').value = from;
  if ($('dateTo')) $('dateTo').value = to;
  document.querySelectorAll('.preset').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.range === preset);
  });
  updateRangeUi({ from, to });
  return { from, to };
}

function applyRangePreset(preset) {
  const today = formatAlgiersDate(new Date());
  if (preset === 'today') {
    return setActiveDateRange(today, today, 'today');
  }
  if (preset === '30') {
    return setActiveDateRange(shiftIsoDate(today, -29), today, '30');
  }
  return setActiveDateRange(shiftIsoDate(today, -6), today, '7');
}

function getActiveDateRange() {
  const from = ($('dateFrom')?.value || '').trim();
  const to = ($('dateTo')?.value || '').trim();
  if (from && to) {
    if (state.dateRange.from !== from || state.dateRange.to !== to) {
      state.dateRange = { from, to };
      state.rangePreset = detectPresetFromDates(from, to);
      document.querySelectorAll('.preset').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.range === state.rangePreset);
      });
    }
    return { from, to };
  }
  if (state.dateRange.from && state.dateRange.to) {
    return { ...state.dateRange };
  }
  return applyRangePreset(state.rangePreset || '7');
}

function metricsQueryString() {
  const { from, to } = getActiveDateRange();
  return `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
}

function getQueryDateRange() {
  const from = ($('dateFrom')?.value || '').trim();
  const to = ($('dateTo')?.value || '').trim();
  if (from && to) return { from, to };
  const today = formatAlgiersDate(new Date());
  return { from: today, to: today };
}

function detectPresetFromDates(from, to) {
  const today = formatAlgiersDate(new Date());
  if (from === today && to === today) return 'today';
  if (to === today && from === shiftIsoDate(today, -6)) return '7';
  if (to === today && from === shiftIsoDate(today, -29)) return '30';
  return 'custom';
}

function applyCustomDateRange(from, to) {
  const preset = detectPresetFromDates(from, to);
  return setActiveDateRange(from, to, preset);
}

function getSelectedRangeLabel(from, to) {
  const start = from || $('dateFrom')?.value;
  const end = to || $('dateTo')?.value;
  if (!start || !end) return '';
  if (start === end) return `اليوم (${start})`;
  return `${start} → ${end}`;
}

function updateRangeUi(range) {
  const from = range?.from || $('dateFrom')?.value;
  const to = range?.to || $('dateTo')?.value;
  const label = getSelectedRangeLabel(from, to);
  const singleDay = from && to && from === to;

  const rangeDisplay = $('rangeDisplay');
  if (rangeDisplay) {
    rangeDisplay.textContent = singleDay
      ? `تقرير اليوم: ${from}`
      : label
        ? `تقرير الفترة: ${label}`
        : '';
  }

  const ordersLabel = $('ordersRangeLabel');
  if (ordersLabel) ordersLabel.textContent = label;

  if ($('pageSubtitle') && (state.currentTab === 'overview' || state.currentTab === 'products' || state.currentTab === 'accounting')) {
    $('pageSubtitle').textContent = singleDay
      ? `اليوم (${from}) — طلبيات créées اليوم فقط`
      : label
        ? `الفترة: ${label} — كل الطلبيات في هاد الفترة`
        : 'اختر الفترة من فوق';
  }
  if (state.currentTab === 'orders' && $('pageSubtitle')) {
    $('pageSubtitle').textContent = label
      ? `الفترة: ${label} — الطلبيات حسب توقيت الجزائر`
      : 'الطلبيات حسب توقيت الجزائر';
  }
  if (state.currentTab === 'deliveries' && $('pageSubtitle')) {
    $('pageSubtitle').textContent = label
      ? `DHD — ${label} — تم التسليم`
      : 'DHD — تم التسليم';
  }
}

function formatApiError(body, status) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item.msg || item.message || String(item)).join(' — ');
  }
  if (status === 401) return 'اسم المستخدم أو كلمة المرور غير صحيحة';
  return `Request failed (${status})`;
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const timeoutMs = options.timeoutMs ?? API_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`${API}${path}`, { ...options, headers, signal: controller.signal });
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error(
        `انتهت مهلة الطلب (${Math.round(timeoutMs / 1000)}ث). جرّب "7 أيام" بدل "اليوم"، أو اضغط Sync now لاحقاً.`
      );
    }
    throw new Error(
      'تعذر الاتصال بالسيرفر. افتح الرابط https://api.confortdz.shop/admin من WiFi أو متصفح آخر، ثم أعد المحاولة.'
    );
  } finally {
    window.clearTimeout(timer);
  }
  if (res.status === 401) {
    if (path !== '/api/admin/login') logout();
    const body = await res.json().catch(() => ({}));
    throw new Error(formatApiError(body, res.status));
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(formatApiError(body, res.status));
  }
  return res.json();
}

function showLogin() {
  setLoading(false);
  $('loginView').classList.remove('hidden');
  $('appView').classList.add('hidden');
}

function showApp() {
  $('loginView').classList.add('hidden');
  $('appView').classList.remove('hidden');
}

function logout() {
  stopOrderAlertPolling();
  state.token = '';
  localStorage.removeItem(TOKEN_KEY);
  showLogin();
}

function unlockOrderAudio() {
  if (state.orderAlerts.audioReady) return;
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    gain.gain.value = 0.0001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.01);
    state.orderAlerts.audioReady = true;
    ctx.close().catch(() => {});
  } catch (err) {
    // Ignore — browser may block until user gesture.
  }
}

function playSaleSound() {
  if (!state.orderAlerts.enabled) return;
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const start = ctx.currentTime;
    const notes = [
      { freq: 880, at: 0, dur: 0.12, vol: 0.22 },
      { freq: 1175, at: 0.1, dur: 0.14, vol: 0.24 },
      { freq: 1568, at: 0.22, dur: 0.28, vol: 0.28 },
    ];

    notes.forEach((note) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.value = note.freq;
      const t = start + note.at;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(note.vol, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + note.dur);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t);
      osc.stop(t + note.dur + 0.02);
    });

    setTimeout(() => ctx.close().catch(() => {}), 700);
  } catch (err) {
    // Ignore audio failures.
  }
}

async function requestOrderNotifications() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') return;
  if (Notification.permission === 'denied') return;
  try {
    await Notification.requestPermission();
  } catch (err) {
    // Ignore.
  }
}

function showOrderToast(order) {
  const stack = $('orderToastStack');
  if (!stack) return;

  const toast = document.createElement('div');
  toast.className = 'order-toast';
  toast.innerHTML = `
    <strong>💰 طلبية جديدة!</strong>
    <span>${order.customer_name} — ${order.product_name || 'منتج'}</span>
    <span>${order.wilaya || ''}</span>
    <div class="amount">${money(order.total_price)}</div>
  `;

  toast.addEventListener('click', async () => {
    toast.remove();
    switchTab('orders');
    try {
      await openOrder(order.order_id);
    } catch (err) {
      showError(err.message);
    }
  });

  stack.prepend(toast);
  setTimeout(() => toast.remove(), 12000);
}

function notifyNewOrder(order) {
  playSaleSound();
  showOrderToast(order);

  if ('Notification' in window && Notification.permission === 'granted') {
    try {
      new Notification('طلبية جديدة — Velora DZ', {
        body: `${order.customer_name} — ${money(order.total_price)}`,
        tag: `order-${order.order_id}`,
      });
    } catch (err) {
      // Ignore.
    }
  }
}

function updateOrderAlertUi() {
  const btn = $('orderAlertToggle');
  const live = $('livePulse');
  if (btn) {
    btn.classList.toggle('active', state.orderAlerts.enabled);
    btn.textContent = state.orderAlerts.enabled ? '🔔 صوت ON' : '🔕 صوت OFF';
  }
  if (live) {
    live.classList.toggle('hidden', !state.token || !state.orderAlerts.enabled);
  }
}

async function pollLatestOrder() {
  if (!state.token || !state.orderAlerts.enabled) return;

  try {
    const data = await api('/api/admin/orders/latest');
    const order = data.order;
    if (!order) return;

    if (!state.orderAlerts.initialized) {
      state.orderAlerts.initialized = true;
      state.orderAlerts.lastOrderDbId = order.id;
      localStorage.setItem('veloradz_last_order_id', String(order.id));
      return;
    }

    if (order.id > state.orderAlerts.lastOrderDbId) {
      state.orderAlerts.lastOrderDbId = order.id;
      localStorage.setItem('veloradz_last_order_id', String(order.id));
      notifyNewOrder(order);
      if (state.currentTab === 'orders') await loadOrders();
      if (state.metrics) await loadMetrics();
    }
  } catch (err) {
    // Silent poll failures — dashboard refresh still works.
  }
}

function startOrderAlertPolling() {
  stopOrderAlertPolling();
  if (!state.orderAlerts.enabled) {
    updateOrderAlertUi();
    return;
  }

  updateOrderAlertUi();
  pollLatestOrder();
  state.orderAlerts.pollTimer = window.setInterval(pollLatestOrder, 12000);
}

function stopOrderAlertPolling() {
  if (state.orderAlerts.pollTimer) {
    clearInterval(state.orderAlerts.pollTimer);
    state.orderAlerts.pollTimer = null;
  }
  state.orderAlerts.initialized = false;
  updateOrderAlertUi();
}

function toggleOrderAlerts() {
  state.orderAlerts.enabled = !state.orderAlerts.enabled;
  localStorage.setItem('veloradz_order_alerts', state.orderAlerts.enabled ? 'on' : 'off');
  if (state.orderAlerts.enabled) {
    unlockOrderAudio();
    requestOrderNotifications();
    startOrderAlertPolling();
  } else {
    stopOrderAlertPolling();
  }
  updateOrderAlertUi();
}

async function login(username, password) {
  const data = await api('/api/admin/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  state.token = data.access_token;
  localStorage.setItem(TOKEN_KEY, state.token);
  unlockOrderAudio();
  await requestOrderNotifications();
  showApp();
  await bootstrap();
  startOrderAlertPolling();
}

function queryRange() {
  return metricsQueryString();
}

async function refreshActiveTabData({ syncDhd = false } = {}) {
  if (syncDhd) await runDhdSync();
  if (state.currentTab === 'overview' || state.currentTab === 'products' || state.currentTab === 'accounting') {
    await loadMetrics(false);
  } else if (state.currentTab === 'orders') {
    await loadOrders();
  } else if (state.currentTab === 'deliveries') {
    await loadDeliveries(false);
  } else if (state.currentTab === 'costs') {
    await loadProducts();
  }
}

async function loadStatuses() {
  state.statuses = await api('/api/admin/statuses');
  $('orderStatus').innerHTML = '<option value="">All statuses</option>' +
    state.statuses.map((s) => `<option value="${s}">${s}</option>`).join('');
  $('modalStatus').innerHTML = state.statuses.map((s) => `<option value="${s}">${s}</option>`).join('');
}

async function loadMetrics(withSync = false) {
  const range = getActiveDateRange();
  const qs = metricsQueryString();
  const syncQs = withSync ? '&sync=true' : '&sync=false';
  state.metrics = await api(`/api/admin/metrics?${qs}${syncQs}`);
  renderOverview(range);
  renderProductPerformance(range);
  renderAccounting();
  updateRangeUi(range);
}

async function loadProducts() {
  state.products = await api('/api/admin/products');
  renderProductCosts();
}

async function loadOrders() {
  const { from, to } = getActiveDateRange();
  if (!from || !to) {
    showError('اختر تاريخ البداية والنهاية');
    return;
  }

  const params = new URLSearchParams({ from, to, limit: '500' });
  if ($('orderSearch').value.trim()) params.set('search', $('orderSearch').value.trim());
  if ($('orderStatus').value) params.set('status', $('orderStatus').value);
  state.orders = await api(`/api/admin/orders?${params.toString()}`);
  renderOrders();
  updateRangeUi();
}

async function loadDeliveries(withSync = false) {
  const { from, to } = getActiveDateRange();
  if (!from || !to) {
    showError('اختر تاريخ البداية والنهاية');
    return;
  }

  const params = new URLSearchParams({ from, to, sync: withSync ? 'true' : 'false' });
  state.deliveries = await api(`/api/admin/deliveries?${params.toString()}`);
  renderDeliveries();
  updateRangeUi();
}

function renderOverview(range) {
  const m = state.metrics;
  if (!m) return;
  const acc = m.accounting || {};
  const from = m.from || range?.from || state.dateRange.from;
  const to = m.to || range?.to || state.dateRange.to;
  const singleDay = m.single_day ?? (from && to && from === to);

  $('mDeliveredRevenue').textContent = money(acc.revenue_delivered || 0);
  $('mNetProfit').textContent = `صافي الربح ${money(acc.net_profit || 0)}`;
  $('mAdSpend').textContent = money(acc.ad_spend_total || 0);
  $('mRoas').textContent = acc.roas || 0;
  if ($('mLoss')) $('mLoss').textContent = money(acc.loss || 0);

  const rangeLabel = getSelectedRangeLabel(from, to);
  if ($('pageSubtitle')) {
    $('pageSubtitle').textContent = singleDay
      ? `اليوم (${from}) — ${acc.orders_total || 0} طلبية créées اليوم`
      : rangeLabel
        ? `الفترة: ${rangeLabel} — ${acc.orders_total || 0} طلبية`
        : 'اختر الفترة من فوق';
  }
  if ($('rangeDisplay')) {
    $('rangeDisplay').textContent = singleDay
      ? `تقرير اليوم: ${from} — ${acc.orders_total || 0} طلبية`
      : `تقرير الفترة: ${rangeLabel} — ${acc.orders_total || 0} طلبية`;
  }

  const cards = [
    ['إجمالي الطلبيات', acc.orders_total || 0],
    ['نسبة التأكيد', pct(acc.confirmation_rate)],
    ['نسبة التسليم', pct(acc.delivery_rate)],
    ['في الانتظار', acc.orders_pending || 0],
    ['مؤكد+', acc.orders_confirmed || 0],
    ['تم الشحن', acc.orders_shipped || 0],
    ['تم التسليم', acc.orders_delivered || 0],
    ['ملغي', acc.orders_cancelled || 0],
    ['إيراد مسلّم', money(acc.revenue_delivered || 0)],
    ['تكلفة المنتج', money(acc.product_cost || 0)],
    ['ربح إجمالي', money(acc.gross_profit || 0)],
    ['صرف إعلانات', money(acc.ad_spend_total || 0)],
    ['ربح صافي', money(acc.net_profit || 0)],
    ['خسارة', money(acc.loss || 0)],
    ['ROAS', acc.roas || 0],
  ];

  $('metricsGrid').innerHTML = cards.map(([label, value]) => `
    <div class="metric-card"><span>${label}</span><strong>${value}</strong></div>
  `).join('');

  const daily = m.daily || [];
  const maxRev = Math.max(...daily.map((d) => d.revenue || 0), 1);
  $('dailyChart').innerHTML = daily.map((d) => `
    <div class="bar-row">
      <span>${d.date.slice(5)}</span>
      <div class="bar-track"><div class="bar-fill green" style="width:${((d.revenue || 0) / maxRev) * 100}%"></div></div>
      <span>${money(d.revenue)}</span>
    </div>
  `).join('') || '<p class="muted">No data yet</p>';

  const channels = m.by_channel || [];
  const maxCh = Math.max(...channels.map((c) => c.revenue || 0), 1);
  $('channelChart').innerHTML = channels.map((c) => `
    <div class="bar-row">
      <span>${c.channel}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${((c.revenue || 0) / maxCh) * 100}%"></div></div>
      <span>${money(c.revenue)}</span>
    </div>
  `).join('') || '<p class="muted">No channel data</p>';

  $('pnlTableBody').innerHTML = (m.daily_pnl || []).map((row) => `
    <tr>
      <td>${row.date}</td>
      <td>${row.orders}</td>
      <td>${money(row.revenue_delivered)}</td>
      <td>${money(row.ad_spend)}</td>
      <td>${money(row.product_cost)}</td>
      <td><strong class="${Number(row.net_profit) >= 0 ? 'text-green' : 'text-red'}">${money(row.net_profit)}</strong></td>
      <td>${money(row.loss || 0)}</td>
    </tr>
  `).join('') || '<tr><td colspan="7">لا توجد بيانات — أضف صرف إعلانات واختر فترة فيها طلبيات</td></tr>';

  renderSyncNote(m.last_sync);
}

function renderSyncNote(lastSync) {
  const el = $('syncStatusNote');
  if (!el || !lastSync) return;
  const dhd = lastSync.dhd || {};
  const meta = lastSync.meta || {};
  const parts = [];
  if (dhd.ok) parts.push(`DHD: ${dhd.updated || 0} محدّث / ${dhd.checked || 0} مفحوص`);
  else if (dhd.reason === 'dhd_not_configured') parts.push('DHD: غير مربوط (DHD_API_TOKEN)');
  if (meta.ok) parts.push(`Meta: ${meta.synced || 0} يوم`);
  else if (meta.reason === 'meta_not_configured') parts.push('Meta: يدوي (أضف الصرف في Comptabilité)');
  el.textContent = parts.join(' · ') || el.textContent;
}

function renderProductPerformance(range) {
  const rows = state.metrics?.product_performance || [];
  const acc = state.metrics?.accounting || {};
  const label = getSelectedRangeLabel(range?.from, range?.to);

  if ($('productPerfNote')) {
    $('productPerfNote').textContent = label
      ? `${label} — شحال بعثنا، شحال ليفرينا، إعلانات، فائدة/خسارة لكل منتج`
      : 'اختر الفترة من فوق';
  }

  if ($('productSummaryCards')) {
    $('productSummaryCards').innerHTML = [
      ['حبات طلب', acc.units_ordered || 0],
      ['حبات شحن', acc.units_shipped || 0],
      ['حبات تسلّم', acc.units_delivered || 0],
      ['إعلانات', money(acc.ad_spend_total || 0)],
      ['ربح صافي', money(acc.net_profit || 0)],
      ['خسارة', money(acc.loss || 0)],
    ].map(([label, value]) => `
      <div class="metric-card"><span>${label}</span><strong>${value}</strong></div>
    `).join('');
  }

  $('productPerfBody').innerHTML = rows.map((p) => {
    const profit = Number(p.net_profit || 0);
    const profitCell = profit >= 0
      ? `<strong class="text-green">${money(profit)}</strong>`
      : '—';
    const lossCell = profit < 0
      ? `<strong class="text-red">${money(p.loss || Math.abs(profit))}</strong>`
      : '—';
    return `
    <tr>
      <td><strong>${p.product_name}</strong></td>
      <td>${p.orders || 0}</td>
      <td>${p.units_ordered || 0}</td>
      <td>${p.units_shipped || 0}</td>
      <td>${p.units_delivered || 0}</td>
      <td>${money(p.delivered_revenue)}</td>
      <td>${money(p.product_cost)}</td>
      <td>${money(p.ad_spend)}</td>
      <td>${money(p.ad_cost_per_delivered)}</td>
      <td>${money(p.final_cost_per_delivered)}</td>
      <td><strong class="${Number(p.net_profit_per_delivered || 0) >= 0 ? 'text-green' : 'text-red'}">${signedMoney(p.net_profit_per_delivered)}</strong></td>
      <td>${profitCell}</td>
      <td>${lossCell}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="13">لا توجد بيانات — اختر فترة فيها طلبيات</td></tr>';
}

function renderAccounting() {
  const m = state.metrics;
  const acc = m?.accounting || {};
  $('accountingSummary').innerHTML = [
    ['إيراد مسلّم', money(acc.revenue_delivered)],
    ['إيراد مؤكد', money(acc.revenue_confirmed)],
    ['تكلفة المنتج', money(acc.product_cost)],
    ['ربح إجمالي', money(acc.gross_profit)],
    ['صرف إعلانات', money(acc.ad_spend_total)],
    ['ربح صافي', money(acc.net_profit)],
    ['خسارة', money(acc.loss || 0)],
    ['إعلان/حبة مسلّمة', money(acc.ad_cost_per_delivered)],
    ['كوست نهائي/حبة', money(acc.final_cost_per_delivered)],
    ['صافي/حبة', signedMoney(acc.net_profit_per_delivered)],
    ['نسبة التأكيد', pct(acc.confirmation_rate)],
    ['نسبة التسليم', pct(acc.delivery_rate)],
    ['ROAS', acc.roas || 0],
  ].map(([k, v]) => `<div class="summary-row"><span>${k}</span><strong>${v}</strong></div>`).join('');

  $('adSpendTableBody').innerHTML = (m?.ad_spend_entries || []).map((row) => `
    <tr>
      <td>${row.spend_date}</td>
      <td>${row.platform}</td>
      <td>${row.product_name || row.product_id || 'كل المنتجات'}</td>
      <td>${money(row.amount_dzd)}</td>
      <td>${row.source || 'manual'}</td>
      <td>${row.notes || '—'}</td>
      <td>${row.source === 'auto' ? '—' : `<button type="button" class="btn btn-soft" data-delete-ad="${row.id}">Delete</button>`}</td>
    </tr>
  `).join('') || '<tr><td colspan="7">No ad spend entries</td></tr>';
}

function renderProductCosts() {
  populateAdProductSelect();
  $('productCostsBody').innerHTML = state.products.map((p) => `
    <tr>
      <td><strong>${p.product_name}</strong><div class="muted small">${p.product_id}</div></td>
      <td><input type="number" min="0" step="1" value="${p.purchase_cost_dzd || 0}" data-cost-id="${p.product_id}" /></td>
      <td><button type="button" class="btn btn-primary" data-save-cost="${p.product_id}">Save</button></td>
    </tr>
  `).join('') || '<tr><td colspan="3">No products</td></tr>';
}

function populateAdProductSelect() {
  const select = $('adProduct');
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">كل المنتجات / صرف عام</option>' +
    state.products.map((p) => `<option value="${p.product_id}">${p.product_name}</option>`).join('');
  select.value = current;
}

function renderOrders() {
  const count = state.orders.length;
  const range = getSelectedRangeLabel();
  const countEl = $('ordersCountLabel');
  if (countEl) {
    countEl.textContent = range
      ? `${count} طلبية في ${range}`
      : `${count} طلبية`;
  }

  $('ordersTableBody').innerHTML = state.orders.map((o) => `
    <tr class="order-row order-row-${statusClass(o.status)}">
      <td><strong>${o.order_id}</strong></td>
      <td>${o.customer_name}<div class="muted small">${o.phone}</div></td>
      <td>${o.product_name}</td>
      <td>${o.wilaya}</td>
      <td>${money(o.total_price)}</td>
      <td><span class="status ${statusClass(o.status)}">${o.status}</span></td>
      <td>${fmtDate(o.created_at)}</td>
      <td><button type="button" class="btn btn-soft" data-order-id="${o.order_id}">View</button></td>
    </tr>
  `).join('') || '<tr><td colspan="8">No orders in this period</td></tr>';
}

function renderDeliveries() {
  const data = state.deliveries || { orders: [], total: 0, revenue_delivered: 0, sync: {} };
  const orders = data.orders || [];
  const range = getSelectedRangeLabel();
  const countEl = $('deliveriesCountLabel');
  const rangeEl = $('deliveriesRangeLabel');
  if (countEl) {
    countEl.textContent = range
      ? `${orders.length} طلبية مسلّمة — ${range}`
      : `${orders.length} طلبية مسلّمة`;
  }
  if (rangeEl) rangeEl.textContent = range ? `الفترة: ${range}` : '';

  const sync = data.sync || {};
  const syncNote = sync.ok === false
    ? (sync.reason === 'dhd_not_configured'
      ? 'DHD غير مربوط — أضف DHD_API_TOKEN'
      : 'فشل الاتصال بـ DHD')
    : `DHD: ${sync.updated || 0} محدّث / ${sync.checked || 0} مفحوص`;
  const syncErrors = (sync.errors || []).length
    ? `<p class="muted small">${sync.errors.join(' · ')}</p>`
    : '';

  $('deliveriesStats').innerHTML = [
    ['تم التسليم', data.total || orders.length],
    ['إيراد مسلّم', money(data.revenue_delivered || 0)],
    ['آخر مزامنة DHD', syncNote],
  ].map(([label, value]) => `
    <div class="metric-card"><span>${label}</span><strong>${value}</strong></div>
  `).join('') + syncErrors;

  $('deliveriesTableBody').innerHTML = orders.map((o) => `
    <tr class="order-row order-row-delivered">
      <td><strong>${o.order_id}</strong></td>
      <td>${o.customer_name}<div class="muted small">${o.phone}</div></td>
      <td dir="ltr">${o.tracking_number || '—'}</td>
      <td>${o.wilaya}</td>
      <td>${money(o.total_price)}</td>
      <td>${fmtDate(o.updated_at || o.created_at)}</td>
      <td><button type="button" class="btn btn-soft" data-order-id="${o.order_id}">View</button></td>
    </tr>
  `).join('') || '<tr><td colspan="7">لا توجد طلبيات مسلّمة في هذه الفترة — جرّب 30 يوم</td></tr>';
}

async function openOrder(orderId) {
  state.selectedOrderId = orderId;
  const o = await api(`/api/admin/orders/${orderId}`);
  $('modalTitle').textContent = o.order_id;
  $('modalSubtitle').textContent = `${fmtDate(o.created_at)} • ${o.wilaya}`;
  $('modalStatus').value = o.status;
  $('orderPreview').innerHTML = `
    <div class="preview-grid">
      <div class="preview-item"><span>Customer</span><strong>${o.customer_name}</strong></div>
      <div class="preview-item"><span>Phone</span><strong dir="ltr">${o.phone}</strong></div>
      <div class="preview-item"><span>Wilaya / Commune</span><strong>${o.wilaya}<br>${o.commune}</strong></div>
      <div class="preview-item"><span>Product</span><strong>${o.product_name} x${o.quantity}</strong></div>
      <div class="preview-item"><span>Total</span><strong>${money(o.total_price)}</strong></div>
      <div class="preview-item"><span>Source</span><strong>${o.utm_source || 'direct'}</strong></div>
      <div class="preview-item"><span>IP / City</span><strong>${o.ip_address || '—'}<br>${o.city || '—'}</strong></div>
      <div class="preview-item"><span>Status</span><strong>${o.status}</strong></div>
      <div class="preview-item"><span>DHD Tracking</span><strong dir="ltr">${o.tracking_number || '—'}</strong></div>
    </div>
  `;
  $('orderModal').classList.remove('hidden');
}

const TAB_TITLES = {
  overview: 'Overview',
  products: 'حساب المنتجات',
  orders: 'Orders',
  deliveries: 'التوصيل DHD',
  accounting: 'Comptabilité',
  costs: 'Product Costs',
};

function switchTab(tab) {
  state.currentTab = tab;
  if (tab === 'deliveries') {
    applyRangePreset('30');
  } else if (state.rangePreset !== 'custom') {
    applyRangePreset(state.rangePreset);
  }
  document.querySelectorAll('.tab').forEach((el) => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.add('hidden');
  });
  const panel = $(`tab-${tab}`);
  if (panel) panel.classList.remove('hidden');
  $('pageTitle').textContent = TAB_TITLES[tab] || 'Admin';
  updateRangeUi(getActiveDateRange());
  refreshCurrentTab();
}

async function runDhdSync() {
  return api('/api/admin/sync/run', { method: 'POST' });
}

async function refreshCurrentTab() {
  setLoading(true);
  showError('');
  try {
    await refreshActiveTabData({ syncDhd: false });
  } catch (err) {
    showError(err.message || 'Failed to load data');
  } finally {
    setLoading(false);
  }
}

async function refreshAll() {
  setLoading(true);
  showError('');
  try {
    await refreshActiveTabData({ syncDhd: false });
  } catch (err) {
    showError(err.message || 'Failed to load data');
  } finally {
    setLoading(false);
  }
}

async function refreshWithDhdSync() {
  setLoading(true);
  showError('');
  try {
    await runDhdSync();
    await refreshActiveTabData({ syncDhd: false });
  } catch (err) {
    showError(err.message || 'Failed to sync data');
  } finally {
    setLoading(false);
  }
}

async function bootstrap() {
  applyRangePreset('7');
  if ($('adDate')) $('adDate').value = formatAlgiersDate(new Date());
  setLoading(true);
  showError('');
  try {
    await loadStatuses();
    await loadMetrics(false);
    setLoading(false);
    await loadProducts().catch((err) => {
      showError(err.message || 'تعذر تحميل تكاليف المنتجات');
    });
  } catch (err) {
    showError(err.message || 'Failed to start dashboard');
  } finally {
    setLoading(false);
  }
}

document.addEventListener('click', async (e) => {
  const target = e.target.closest('[data-tab],[data-order-id],[data-save-cost],[data-delete-ad]');
  if (!target) return;

  if (target.dataset.tab) {
    switchTab(target.dataset.tab);
    return;
  }

  if (target.dataset.orderId) {
    try {
      setLoading(true);
      await openOrder(target.dataset.orderId);
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
    return;
  }

  if (target.dataset.saveCost) {
    const input = document.querySelector(`input[data-cost-id="${target.dataset.saveCost}"]`);
    try {
      setLoading(true);
      await api(`/api/admin/products/${target.dataset.saveCost}`, {
        method: 'PATCH',
        body: JSON.stringify({ purchase_cost_dzd: Number(input?.value || 0) }),
      });
      await loadMetrics();
      await loadProducts();
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
    return;
  }

  if (target.dataset.deleteAd) {
    try {
      setLoading(true);
      await api(`/api/admin/ad-spend/${target.dataset.deleteAd}`, { method: 'DELETE' });
      await loadMetrics();
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
  }
});

$('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('loginError').classList.add('hidden');
  try {
    await login($('username').value.trim(), $('password').value);
  } catch (err) {
    $('loginError').textContent = err.message;
    $('loginError').classList.remove('hidden');
  }
});

$('logoutBtn').addEventListener('click', logout);
if ($('orderAlertToggle')) {
  $('orderAlertToggle').addEventListener('click', toggleOrderAlerts);
}
$('applyFilters').addEventListener('click', refreshAll);
['dateFrom', 'dateTo'].forEach((id) => {
  const input = $(id);
  if (!input) return;
  input.addEventListener('change', async () => {
    const from = ($('dateFrom')?.value || '').trim();
    const to = ($('dateTo')?.value || '').trim();
    if (!from || !to) return;
    applyCustomDateRange(from, to);
    setLoading(true);
    showError('');
    try {
      await refreshActiveTabData({ syncDhd: state.currentTab === 'orders' });
    } catch (err) {
      showError(err.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  });
});
document.querySelectorAll('.preset').forEach((btn) => {
  btn.addEventListener('click', async () => {
    applyRangePreset(btn.dataset.range);
    setLoading(true);
    showError('');
    try {
      await refreshActiveTabData({ syncDhd: false });
    } catch (err) {
      showError(err.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  });
});
$('reloadOrders').addEventListener('click', loadOrders);
$('reloadDeliveries').addEventListener('click', loadDeliveries);
$('orderSearch').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadOrders(); });
$('orderStatus').addEventListener('change', loadOrders);
$('closeModal').addEventListener('click', () => $('orderModal').classList.add('hidden'));
$('saveStatusBtn').addEventListener('click', async () => {
  try {
    setLoading(true);
    await api(`/api/admin/orders/${state.selectedOrderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: $('modalStatus').value }),
    });
    $('orderModal').classList.add('hidden');
    await refreshAll();
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
});

$('adSpendForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const amountDzd = resolveAdSpendDzd();
  if (!amountDzd || amountDzd <= 0) {
    showError('أدخل مبلغ الإعلانات ($ أو دج)');
    return;
  }
  try {
    setLoading(true);
    const usd = Number($('adAmountUsd')?.value || 0);
    const noteExtra = usd > 0 ? ` ($${usd})` : '';
    const productId = $('adProduct')?.value || '';
    const product = state.products.find((p) => p.product_id === productId);
    await api('/api/admin/ad-spend', {
      method: 'POST',
      body: JSON.stringify({
        spend_date: $('adDate').value,
        platform: $('adPlatform').value,
        product_id: productId || null,
        product_name: product?.product_name || null,
        amount_dzd: amountDzd,
        notes: (($('adNotes').value.trim() || '') + noteExtra).trim() || null,
      }),
    });
    $('adAmount').value = '';
    if ($('adAmountUsd')) $('adAmountUsd').value = '';
    $('adNotes').value = '';
    await loadMetrics();
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
});

$('runSyncBtn').addEventListener('click', async () => {
  const btn = $('runSyncBtn');
  btn.disabled = true;
  btn.textContent = 'Syncing...';
  try {
    await refreshWithDhdSync();
    alert('Sync OK — الأرقام محدّثة');
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sync now';
  }
});

if (state.token) {
  showApp();
  unlockOrderAudio();
  bootstrap().then(() => startOrderAlertPolling());
} else {
  showLogin();
}
updateOrderAlertUi();
