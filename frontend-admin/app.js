/* =========================================================
   NAVIGATION
   ========================================================= */
function goToScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  window.scrollTo(0, 0);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* =========================================================
   AUTH
   Own localStorage key (attune_admin_token) — same reasoning as the
   other two frontends: all three run under one origin and must never
   clobber each other's session.
   ========================================================= */
const TOKEN_KEY = 'attune_admin_token';
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function handleLogin(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('login-error');
  errorEl.style.display = 'none';
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  const form = new URLSearchParams();
  form.set('username', email);
  form.set('password', password);
  try {
    const res = await fetch('/api/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Incorrect email or password');
    const { access_token } = await res.json();
    setToken(access_token);
    updateNav();
    openDashboard();
  } catch (err) {
    errorEl.textContent = err.message || 'Something went wrong.';
    errorEl.style.display = 'block';
  }
}

function logout() {
  clearToken();
  updateNav();
  goToScreen('login');
}

function updateNav() {
  const loggedIn = !!getToken();
  document.getElementById('nav-actions').style.display = loggedIn ? 'flex' : 'none';
}

/* =========================================================
   API
   ========================================================= */
async function apiFetch(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    logout();
    throw new Error('Session expired — please log in again.');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* =========================================================
   DASHBOARD
   ========================================================= */
async function openDashboard() {
  goToScreen('dashboard');
  const el = document.getElementById('metrics-grid');
  el.innerHTML = '<p class="empty-copy">Loading…</p>';
  try {
    const m = await apiFetch('/api/admin/metrics');
    const statusList = (obj) => Object.entries(obj).map(([k, v]) => `${escapeHtml(k)}: ${v}`).join(' · ') || 'none yet';
    el.innerHTML = `
      <div class="metric-card">
        <p class="metric-label">Instructors</p>
        <p class="metric-value">${m.active_instructors}<span style="font-size:16px; color:var(--muted);"> / ${m.total_instructors}</span></p>
        <p class="metric-breakdown">active / total</p>
      </div>
      <div class="metric-card">
        <p class="metric-label">Customers</p>
        <p class="metric-value">${m.active_customers}<span style="font-size:16px; color:var(--muted);"> / ${m.total_customers}</span></p>
        <p class="metric-breakdown">not suspended / total</p>
      </div>
      <div class="metric-card">
        <p class="metric-label">Match rate (30d)</p>
        <p class="metric-value">${m.match_rate_30d != null ? Math.round(m.match_rate_30d * 100) + '%' : '—'}</p>
        <p class="metric-breakdown">confirmed ÷ (confirmed + unmatched)</p>
      </div>
      <div class="metric-card">
        <p class="metric-label">Packages by status</p>
        <p class="metric-breakdown" style="margin-top:10px; font-size:13.5px;">${statusList(m.bookings_by_status)}</p>
      </div>
      <div class="metric-card">
        <p class="metric-label">Scheduled lessons by status</p>
        <p class="metric-breakdown" style="margin-top:10px; font-size:13.5px;">${statusList(m.lesson_requests_by_status)}</p>
      </div>`;
  } catch (err) {
    el.innerHTML = `<p class="empty-copy">Couldn't load metrics: ${escapeHtml(err.message)}</p>`;
  }
}

/* =========================================================
   INSTRUCTORS
   ========================================================= */
async function openInstructors() {
  goToScreen('instructors');
  await loadInstructors();
}

async function loadInstructors() {
  const listEl = document.getElementById('instructors-list');
  const active = document.getElementById('instructor-filter-active').value;
  const suspended = document.getElementById('instructor-filter-suspended').value;
  const params = new URLSearchParams();
  if (active) params.set('active', active);
  if (suspended) params.set('suspended', suspended);
  listEl.innerHTML = '<p class="empty-copy">Loading…</p>';
  try {
    const instructors = await apiFetch(`/api/admin/instructors?${params.toString()}`);
    listEl.innerHTML = instructors.length
      ? instructors.map(instructorRowHTML).join('')
      : '<p class="empty-copy">No instructors match these filters.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy">${escapeHtml(err.message)}</p>`;
  }
}

function instructorRowHTML(i) {
  const activePill = i.active
    ? '<span class="status-pill status-active">Active</span>'
    : '<span class="status-pill status-inactive">Inactive</span>';
  const suspendedPill = i.suspended ? '<span class="status-pill status-suspended">Suspended</span>' : '';
  const rating = i.review_count > 0 ? `★ ${i.average_rating.toFixed(1)} (${i.review_count})` : 'No reviews yet';
  return `
    <div>
      <div class="admin-row">
        <div class="admin-row-main">
          <p class="admin-row-title">${escapeHtml(i.name)} ${activePill} ${suspendedPill}</p>
          <p class="admin-row-meta">${escapeHtml(i.email)} · ${escapeHtml(i.phone)}<br>${escapeHtml(i.specialty)} · ${escapeHtml(i.city || 'no city set')} · ${escapeHtml(rating)}${i.suspension_reason ? `<br>Reason: ${escapeHtml(i.suspension_reason)}` : ''}</p>
        </div>
        <div class="admin-row-actions">
          ${i.suspended
            ? `<button class="btn btn-outline btn-sm" onclick="unsuspendInstructor(${i.id})">Unsuspend</button>`
            : `<button class="btn btn-danger btn-sm" onclick="toggleSuspendForm('instructors', ${i.id})">Suspend</button>`}
        </div>
      </div>
      ${suspendFormHTML('instructors', i.id)}
    </div>`;
}

function suspendFormHTML(kind, id) {
  return `
    <div class="suspend-inline-form" id="suspend-form-${kind}-${id}" style="display:none;">
      <input class="field-input" id="suspend-reason-${kind}-${id}" placeholder="Reason (optional, shown to them)">
      <button class="btn btn-danger btn-sm" onclick="confirmSuspend('${kind}', ${id})">Confirm Suspend</button>
      <button class="btn btn-outline btn-sm" onclick="toggleSuspendForm('${kind}', ${id})">Cancel</button>
    </div>`;
}

function toggleSuspendForm(kind, id) {
  const el = document.getElementById(`suspend-form-${kind}-${id}`);
  el.style.display = el.style.display === 'flex' ? 'none' : 'flex';
}

async function confirmSuspend(kind, id) {
  const reason = document.getElementById(`suspend-reason-${kind}-${id}`).value.trim() || null;
  try {
    await apiFetch(`/api/admin/${kind}/${id}/suspend`, { method: 'PUT', body: JSON.stringify({ reason }) });
    if (kind === 'instructors') await loadInstructors(); else await loadCustomers();
  } catch (err) {
    alert(err.message || 'Could not suspend.');
  }
}

async function unsuspendInstructor(id) {
  try {
    await apiFetch(`/api/admin/instructors/${id}/unsuspend`, { method: 'PUT' });
    await loadInstructors();
  } catch (err) {
    alert(err.message || 'Could not unsuspend this instructor.');
  }
}

/* =========================================================
   CUSTOMERS
   ========================================================= */
async function openCustomers() {
  goToScreen('customers');
  await loadCustomers();
}

async function loadCustomers() {
  const listEl = document.getElementById('customers-list');
  const suspended = document.getElementById('customer-filter-suspended').value;
  const params = new URLSearchParams();
  if (suspended) params.set('suspended', suspended);
  listEl.innerHTML = '<p class="empty-copy">Loading…</p>';
  try {
    const customers = await apiFetch(`/api/admin/customers?${params.toString()}`);
    listEl.innerHTML = customers.length
      ? customers.map(customerRowHTML).join('')
      : '<p class="empty-copy">No customers match these filters.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy">${escapeHtml(err.message)}</p>`;
  }
}

function customerRowHTML(c) {
  const suspendedPill = c.suspended ? '<span class="status-pill status-suspended">Suspended</span>' : '';
  return `
    <div>
      <div class="admin-row">
        <div class="admin-row-main">
          <p class="admin-row-title">${escapeHtml(c.name)} ${suspendedPill}</p>
          <p class="admin-row-meta">${escapeHtml(c.email)} · ${escapeHtml(c.phone)}<br>${escapeHtml(c.city || 'no city set')}${c.suspension_reason ? `<br>Reason: ${escapeHtml(c.suspension_reason)}` : ''}</p>
        </div>
        <div class="admin-row-actions">
          ${c.suspended
            ? `<button class="btn btn-outline btn-sm" onclick="unsuspendCustomer(${c.id})">Unsuspend</button>`
            : `<button class="btn btn-danger btn-sm" onclick="toggleSuspendForm('customers', ${c.id})">Suspend</button>`}
        </div>
      </div>
      ${suspendFormHTML('customers', c.id)}
    </div>`;
}

async function unsuspendCustomer(id) {
  try {
    await apiFetch(`/api/admin/customers/${id}/unsuspend`, { method: 'PUT' });
    await loadCustomers();
  } catch (err) {
    alert(err.message || 'Could not unsuspend this customer.');
  }
}

/* =========================================================
   REQUESTS (bookings + lesson requests)
   ========================================================= */
let requestsTab = 'package';

async function openRequests() {
  goToScreen('requests');
  await loadRequests();
}

function setRequestsTab(tab) {
  requestsTab = tab;
  document.getElementById('requests-tab-package').classList.toggle('active', tab === 'package');
  document.getElementById('requests-tab-schedule').classList.toggle('active', tab === 'schedule');
  loadRequests();
}

async function loadRequests() {
  const listEl = document.getElementById('requests-list');
  const status = document.getElementById('requests-filter-status').value;
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  listEl.innerHTML = '<p class="empty-copy">Loading…</p>';
  const path = requestsTab === 'package' ? '/api/admin/bookings' : '/api/admin/lesson-requests';
  try {
    const items = await apiFetch(`${path}?${params.toString()}`);
    listEl.innerHTML = items.length
      ? items.map(requestRowHTML).join('')
      : '<p class="empty-copy">Nothing matches these filters.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy">${escapeHtml(err.message)}</p>`;
  }
}

function requestRowHTML(r) {
  const statusPill = `<span class="status-pill status-${r.status}">${escapeHtml(r.status.replace(/_/g, ' '))}</span>`;
  const dateStr = r.created_at ? new Date(r.created_at).toLocaleDateString() : '';
  const specialtyLabel = r.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  // A still-pending multi-window request has no requested_day yet — see
  // models.LessonRequest's docstring — so this needs a null guard now.
  const packageNote = r.package ? `${escapeHtml(r.package)}, ${r.sessions_total} session${r.sessions_total > 1 ? 's' : ''} · ` : '';
  const detail = requestsTab === 'package'
    ? `${escapeHtml(r.package)} · $${r.amount_paid}`
    : r.requested_day != null
      ? `${packageNote}${r.duration_minutes} min · ${DAY_NAMES[r.requested_day]} ${r.requested_start_time}–${r.requested_end_time} · $${r.amount_paid}`
      : `${packageNote}${r.duration_minutes} min · windows pending match · $${r.amount_paid}`;
  const canCancel = r.status !== 'cancelled_by_admin';
  const cancelCall = requestsTab === 'package' ? `forceCancelBooking(${r.id})` : `forceCancelLessonRequest(${r.id})`;
  return `
    <div class="admin-row">
      <div class="admin-row-main">
        <p class="admin-row-title">${escapeHtml(r.customer_name)} → ${r.instructor_name ? escapeHtml(r.instructor_name) : 'unmatched'} ${statusPill}</p>
        <p class="admin-row-meta">${escapeHtml(specialtyLabel)} · ${detail} · ${escapeHtml(dateStr)}</p>
      </div>
      <div class="admin-row-actions">
        ${canCancel ? `<button class="btn btn-danger btn-sm" onclick="${cancelCall}">Force Cancel</button>` : ''}
      </div>
    </div>`;
}

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

async function forceCancelBooking(id) {
  if (!confirm('Force-cancel this package request? This cannot be undone from here.')) return;
  try {
    await apiFetch(`/api/admin/bookings/${id}/force-cancel`, { method: 'PUT' });
    await loadRequests();
  } catch (err) {
    alert(err.message || 'Could not cancel this request.');
  }
}

async function forceCancelLessonRequest(id) {
  if (!confirm('Force-cancel this scheduled lesson? This cannot be undone from here.')) return;
  try {
    await apiFetch(`/api/admin/lesson-requests/${id}/force-cancel`, { method: 'PUT' });
    await loadRequests();
  } catch (err) {
    alert(err.message || 'Could not cancel this request.');
  }
}

/* =========================================================
   CLIENT DELETION REQUESTS
   ========================================================= */
async function openDeletionRequests() {
  goToScreen('deletions');
  await loadDeletionRequests();
}

async function loadDeletionRequests() {
  const listEl = document.getElementById('deletions-list');
  listEl.innerHTML = '<p class="empty-copy">Loading…</p>';
  try {
    const requests = await apiFetch('/api/admin/client-deletion-requests');
    listEl.innerHTML = requests.length
      ? requests.map(deletionRequestRowHTML).join('')
      : '<p class="empty-copy">No pending deletion requests.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy">${escapeHtml(err.message)}</p>`;
  }
}

function deletionRequestRowHTML(r) {
  const dateStr = r.requested_at ? new Date(r.requested_at).toLocaleDateString() : '';
  return `
    <div class="admin-row">
      <div class="admin-row-main">
        <p class="admin-row-title">${escapeHtml(r.client_name)}</p>
        <p class="admin-row-meta">Requested by ${escapeHtml(r.instructor_name)} · ${escapeHtml(dateStr)}</p>
      </div>
      <div class="admin-row-actions">
        <button class="btn btn-outline btn-sm" onclick="denyDeletion(${r.id})">Deny</button>
        <button class="btn btn-danger btn-sm" onclick="approveDeletion(${r.id})">Approve</button>
      </div>
    </div>`;
}

async function approveDeletion(id) {
  if (!confirm('Approve this deletion? The client (and their lesson history) will be permanently removed.')) return;
  try {
    await apiFetch(`/api/admin/client-deletion-requests/${id}/approve`, { method: 'PUT' });
    await loadDeletionRequests();
  } catch (err) {
    alert(err.message || 'Could not approve this request.');
  }
}

async function denyDeletion(id) {
  try {
    await apiFetch(`/api/admin/client-deletion-requests/${id}/deny`, { method: 'PUT' });
    await loadDeletionRequests();
  } catch (err) {
    alert(err.message || 'Could not deny this request.');
  }
}

/* =========================================================
   REPORTS
   Unlike deletion requests, resolving a report doesn't remove it — it
   just flips `resolved`, so the default filter is "Open" but Resolved/All
   stay one click away for reviewing history.
   ========================================================= */
async function openReports() {
  goToScreen('reports');
  await loadReports();
}

async function loadReports() {
  const listEl = document.getElementById('reports-list');
  listEl.innerHTML = '<p class="empty-copy">Loading…</p>';
  const resolved = document.getElementById('reports-filter-resolved').value;
  const query = resolved ? `?resolved=${resolved}` : '';
  try {
    const reports = await apiFetch(`/api/admin/reports${query}`);
    listEl.innerHTML = reports.length
      ? reports.map(reportRowHTML).join('')
      : '<p class="empty-copy">No reports match this filter.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy">${escapeHtml(err.message)}</p>`;
  }
}

function reportRowHTML(r) {
  const dateStr = r.created_at ? new Date(r.created_at).toLocaleDateString() : '';
  const reporterLabel = r.reporter_type === 'instructor' ? 'Instructor' : 'Customer';
  const reportedLabel = r.reported_type === 'instructor' ? 'instructor' : 'customer';
  return `
    <div class="admin-row">
      <div class="admin-row-main">
        <p class="admin-row-title">${escapeHtml(r.reporter_name)} (${reporterLabel}) reported ${escapeHtml(r.reported_name)} (${reportedLabel})</p>
        <p class="admin-row-meta">${escapeHtml(r.reason)}${r.message ? ' — ' + escapeHtml(r.message) : ''} · ${escapeHtml(dateStr)}${r.resolved ? ' · Resolved' : ''}</p>
      </div>
      ${!r.resolved ? `
      <div class="admin-row-actions">
        <button class="btn btn-outline btn-sm" onclick="resolveReport(${r.id})">Mark Resolved</button>
      </div>` : ''}
    </div>`;
}

async function resolveReport(id) {
  try {
    await apiFetch(`/api/admin/reports/${id}/resolve`, { method: 'PUT' });
    await loadReports();
  } catch (err) {
    alert(err.message || 'Could not resolve this report.');
  }
}

/* =========================================================
   FAQS
   ========================================================= */
async function openFaqs() {
  goToScreen('faqs');
  document.getElementById('faq-form-block').style.display = 'none';
  await loadFaqs();
}

async function loadFaqs() {
  const listEl = document.getElementById('faqs-list');
  listEl.innerHTML = '<p class="empty-copy">Loading…</p>';
  try {
    const faqs = await apiFetch('/api/admin/faqs');
    listEl.innerHTML = faqs.length ? faqs.map(faqRowHTML).join('') : '<p class="empty-copy">No FAQs yet.</p>';
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy">${escapeHtml(err.message)}</p>`;
  }
}

function faqRowHTML(f) {
  return `
    <div class="admin-row">
      <div class="admin-row-main">
        <p class="admin-row-title">${escapeHtml(f.question)}</p>
        <p class="admin-row-meta">${escapeHtml(f.category)}</p>
      </div>
      <div class="admin-row-actions">
        <button class="btn btn-outline btn-sm" onclick="openFaqForm(${f.id}, '${encodeURIComponent(f.question)}', '${f.category}')">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteFaq(${f.id})">Delete</button>
      </div>
    </div>`;
}

function openFaqForm(id, encodedQuestion, category) {
  const block = document.getElementById('faq-form-block');
  const question = encodedQuestion ? decodeURIComponent(encodedQuestion) : '';
  block.style.display = 'block';
  block.innerHTML = `
    <div class="card wizard-card" style="margin:0;">
      <h2 class="card-title" style="font-size:18px;">${id ? 'Edit FAQ' : 'New FAQ'}</h2>
      <div id="faq-form-error" class="form-error" style="display:none;"></div>
      <label class="field-label">Question</label>
      <textarea class="field-textarea" id="faq-question-input">${escapeHtml(question)}</textarea>
      <label class="field-label">Category</label>
      <select class="field-select" id="faq-category-input">
        <option value="app use" ${category === 'app use' ? 'selected' : ''}>App use</option>
        <option value="payments" ${category === 'payments' ? 'selected' : ''}>Payments</option>
        <option value="cancellations" ${category === 'cancellations' ? 'selected' : ''}>Cancellations</option>
      </select>
      <button class="btn btn-primary btn-block" style="margin-top:16px;" onclick="submitFaqForm(${id || 'null'})">${id ? 'Save' : 'Create'}</button>
    </div>`;
}

async function submitFaqForm(id) {
  const errorEl = document.getElementById('faq-form-error');
  errorEl.style.display = 'none';
  const payload = {
    question: document.getElementById('faq-question-input').value.trim(),
    category: document.getElementById('faq-category-input').value,
  };
  if (!payload.question) {
    errorEl.textContent = 'A question is required.';
    errorEl.style.display = 'block';
    return;
  }
  try {
    if (id) {
      await apiFetch(`/api/admin/faqs/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await apiFetch('/api/admin/faqs', { method: 'POST', body: JSON.stringify(payload) });
    }
    document.getElementById('faq-form-block').style.display = 'none';
    await loadFaqs();
  } catch (err) {
    errorEl.textContent = err.message || 'Could not save this FAQ.';
    errorEl.style.display = 'block';
  }
}

async function deleteFaq(id) {
  if (!confirm('Delete this FAQ?')) return;
  try {
    await apiFetch(`/api/admin/faqs/${id}`, { method: 'DELETE' });
    await loadFaqs();
  } catch (err) {
    alert(err.message || 'Could not delete this FAQ.');
  }
}

/* =========================================================
   BOOT
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
  updateNav();
  if (getToken()) {
    openDashboard();
  }
});
