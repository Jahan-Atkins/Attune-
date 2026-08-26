/* =========================================================
   NAVIGATION
   ========================================================= */
function goToScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.screen === name));
}
function setSubtab(group, name) {
  const scope = group === 'sessions' ? '#screen-sessions' : '#screen-clients';
  const root = document.querySelector(scope);
  root.querySelectorAll('.subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === name));
  root.querySelectorAll('.subtab-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === name));
}
function setLearnTab(name, evt) {
  document.querySelectorAll('.utab').forEach(b => b.classList.remove('active'));
  (evt || window.event).currentTarget.classList.add('active');
  document.getElementById('learn-faq').classList.toggle('active', name === 'faq');
  document.getElementById('learn-contact').classList.toggle('active', name === 'contact');
}

/* =========================================================
   SMALL HELPERS
   ========================================================= */
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeAttr(str) {
  return escapeHtml(str).replace(/"/g, '&quot;');
}
function initialsFromName(name) {
  return (name || '').split(' ').filter(Boolean).map(w => w[0].toUpperCase()).slice(0, 2).join('') || '··';
}

/* =========================================================
   AUTH
   Token lives in localStorage — fine here because this app is
   served from its own origin by our own backend, not embedded
   in a third-party sandboxed iframe.
   ========================================================= */
const TOKEN_KEY = 'attune_token';
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

let authMode = 'login';

function toggleAuthMode() {
  authMode = authMode === 'login' ? 'signup' : 'login';
  const isSignup = authMode === 'signup';
  document.getElementById('signup-name-field').style.display = isSignup ? 'block' : 'none';
  document.getElementById('auth-email-note').style.display = isSignup ? 'inline' : 'none';
  document.getElementById('auth-name').required = isSignup;
  document.getElementById('auth-phone').required = isSignup;
  document.getElementById('auth-terms').checked = false;
  document.getElementById('login-sub').textContent = isSignup ? "Create your instructor account" : "Log in to your instructor account";
  document.getElementById('auth-submit-btn').textContent = isSignup ? 'Create Account' : 'Log In';
  document.getElementById('auth-toggle-btn').textContent = isSignup ? 'Already have an account? Log in' : 'New here? Create an account';
  document.getElementById('forgot-password-btn').style.display = isSignup ? 'none' : 'block';
  document.getElementById('login-error').style.display = 'none';
}

/* =========================================================
   FORGOT / RESET PASSWORD
   Unauthenticated, so these use plain fetch (not apiFetch, which
   attaches a token and would log the user out on a 401 that isn't
   actually about their session).
   ========================================================= */
function openForgotPasswordModal() {
  const body = `
    <p class="card-body" style="margin-bottom:16px;">Enter your account email and we'll send a link to reset your password.</p>
    <form id="forgot-password-form" onsubmit="submitForgotPasswordForm(event)">
      <label class="field-label">Email</label>
      <input class="field-input" type="email" id="fp-email" required>
      <div id="fp-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <div id="fp-success" style="display:none; margin-top:12px; color:var(--sage-dark, #4a6a5a);">If an account exists for that email, a reset link has been sent.</div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Send Reset Link</button>
    </form>`;
  openModal('Reset Password', body);
}

async function submitForgotPasswordForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('fp-error');
  const successEl = document.getElementById('fp-success');
  errorEl.style.display = 'none';
  const email = document.getElementById('fp-email').value.trim();
  try {
    const res = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Something went wrong.');
    document.getElementById('forgot-password-form').style.display = 'none';
    successEl.style.display = 'block';
  } catch (err) {
    errorEl.textContent = err.message || 'Something went wrong.';
    errorEl.style.display = 'block';
  }
}

function openResetPasswordModal(token) {
  const body = `
    <p class="card-body" style="margin-bottom:16px;">Choose a new password for your account.</p>
    <form id="reset-password-form" onsubmit="submitResetPasswordForm(event, '${escapeAttr(token)}')">
      <label class="field-label">New password</label>
      <input class="field-input" type="password" id="rp-password" required>
      <div id="rp-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Update Password</button>
    </form>`;
  openModal('Set a New Password', body);
}

async function submitResetPasswordForm(evt, token) {
  evt.preventDefault();
  const errorEl = document.getElementById('rp-error');
  errorEl.style.display = 'none';
  const newPassword = document.getElementById('rp-password').value;
  try {
    const res = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'That reset link is invalid or has expired.');
    closeModal();
    document.getElementById('login-error').textContent = 'Password updated. Log in with your new password.';
    document.getElementById('login-error').style.display = 'block';
  } catch (err) {
    errorEl.textContent = err.message || 'That reset link is invalid or has expired.';
    errorEl.style.display = 'block';
  }
}

async function handleAuthSubmit(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('login-error');
  errorEl.style.display = 'none';
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;

  try {
    let token;
    if (authMode === 'signup') {
      const name = document.getElementById('auth-name').value.trim();
      const phone = document.getElementById('auth-phone').value.trim();
      if (!document.getElementById('auth-terms').checked) {
        errorEl.textContent = 'Please agree to the Terms of Service and Privacy Policy to create an account.';
        errorEl.style.display = 'block';
        return;
      }
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, phone, password }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not sign up');
      token = (await res.json()).access_token;
    } else {
      // OAuth2's password flow expects form-encoded data with the fields
      // named "username" and "password" — that's a spec detail, not
      // something specific to this app.
      const form = new URLSearchParams();
      form.set('username', email);
      form.set('password', password);
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Incorrect email or password');
      token = (await res.json()).access_token;
    }
    setToken(token);
    await boot();
  } catch (err) {
    errorEl.textContent = err.message || 'Something went wrong.';
    errorEl.style.display = 'block';
  }
}

function logout() {
  clearToken();
  document.getElementById('login-screen').classList.remove('hidden');
  goToScreen('home');
}

/* =========================================================
   GOOGLE SIGN-IN
   Only renders a button if the backend reports a configured
   GOOGLE_CLIENT_ID (see main.py's GET /api/config) — a deployment with
   no client ID set just shows the normal email/password form, not a
   broken button. See google_auth.py's module docstring for why this
   never applies to Admin accounts (no equivalent on frontend-admin).
   ========================================================= */
async function initGoogleSignIn() {
  let config;
  try {
    config = await (await fetch('/api/config')).json();
  } catch (err) {
    return; // no config endpoint reachable yet — fail quiet, form still works
  }
  if (!config.google_client_id || typeof google === 'undefined') return;

  google.accounts.id.initialize({
    client_id: config.google_client_id,
    callback: handleGoogleCredential,
  });
  google.accounts.id.renderButton(document.getElementById('google-signin-btn'), {
    theme: 'outline', size: 'large', width: 280,
  });
  document.getElementById('google-signin-wrap').style.display = 'block';
}

async function handleGoogleCredential(response) {
  const errorEl = document.getElementById('login-error');
  errorEl.style.display = 'none';
  try {
    const res = await fetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: response.credential }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not sign in with Google.');
    setToken((await res.json()).access_token);
    await boot();
  } catch (err) {
    errorEl.textContent = err.message || 'Something went wrong.';
    errorEl.style.display = 'block';
  }
}

/* =========================================================
   API LAYER
   Same-origin requests to our own FastAPI backend. apiFetch
   attaches the auth token automatically and logs the user out
   if the token is missing/expired (a 401 response).
   ========================================================= */
async function apiFetch(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    logout();
    throw new Error('Session expired. Please log in again.');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* =========================================================
   MODAL
   ========================================================= */
function openModal(title, bodyHtml) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-backdrop').classList.remove('hidden');
}
function closeModal() {
  document.getElementById('modal-backdrop').classList.add('hidden');
  document.getElementById('modal-body').innerHTML = '';
}

/* =========================================================
   HOME
   ========================================================= */
async function loadSummary() {
  try {
    const summary = await apiFetch('/api/summary');
    document.getElementById('greeting-name').textContent = summary.greeting_name;
    document.getElementById('earned-amount').textContent = `$${summary.earned_this_week}`;

    const info = document.getElementById('home-client-info');
    const empty = document.getElementById('home-client-empty');
    if (summary.current_client_name) {
      document.getElementById('home-client-avatar').textContent = summary.current_client_initials.slice(0, 1);
      document.getElementById('home-client-name').textContent = summary.current_client_name;
      info.style.display = 'flex';
      empty.style.display = 'none';
    } else {
      info.style.display = 'none';
      empty.style.display = 'block';
    }
  } catch (err) {
    console.error('Failed to load summary:', err);
  }
}

/* =========================================================
   CLIENTS
   ========================================================= */
let clientsCache = {};

function clientCardHTML(c) {
  clientsCache[c.id] = c;
  const pct = c.sessions_total ? Math.round((c.sessions_completed / c.sessions_total) * 100) : 0;
  return `
    <div class="client-card" onclick="openClientDetail(${c.id})" style="cursor:pointer;">
      <div class="client-row">
        <div style="display:flex; gap:14px;">
          <div class="avatar avatar-sm avatar-${c.avatar_variant}">${escapeHtml(c.initials)}</div>
          <div>
            <p class="client-name">${escapeHtml(c.name)}</p>
            <p class="client-id">ID ${String(c.id).padStart(6, '0')}</p>
          </div>
        </div>
        <div>
          <p class="next-label">Next session</p>
          <p class="next-value">${c.next_session ? escapeHtml(c.next_session) : 'None scheduled'}</p>
        </div>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
      <p class="progress-text"><b>${c.sessions_completed}</b> of ${c.sessions_total} sessions completed · <b>$${c.amount_paid}</b> of $${c.amount_total} paid</p>
    </div>`;
}

let clientSortAsc = true;

function toggleClientSort() {
  clientSortAsc = !clientSortAsc;
  const active = document.querySelector('#screen-clients .subtab.active').dataset.subtab;
  loadClients(active);
}

function toggleClientSearch() {
  const input = document.getElementById('clients-search-input');
  const showing = input.style.display !== 'none';
  input.style.display = showing ? 'none' : 'block';
  if (showing) { input.value = ''; filterClients(); } else { input.focus(); }
}

function filterClients() {
  const q = document.getElementById('clients-search-input').value.trim().toLowerCase();
  document.querySelectorAll('#screen-clients .client-card').forEach(card => {
    card.style.display = card.querySelector('.client-name').textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

async function loadClients(status) {
  const listEl = document.getElementById(`clients-${status}-list`);
  const emptyEl = document.getElementById(`clients-${status}-empty`);
  try {
    const data = await apiFetch(`/api/clients?status=${status}`);
    data.sort((a, b) => clientSortAsc ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name));
    if (data.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = data.map(clientCardHTML).join('');
      emptyEl.style.display = 'none';
      filterClients(); // keep an active search applied across a re-sort/re-load
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.querySelector('.empty-copy').textContent = "Couldn't load clients. Is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load clients:', err);
  }
}

const DAY_ABBR = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

function openClientForm(id) {
  const c = id ? clientsCache[id] : null;
  const isEdit = !!c;
  const selectedDays = c && c.available_days ? c.available_days.split(',').map(Number) : [];
  const body = `
    <form id="client-form" onsubmit="submitClientForm(event, ${id || 'null'})">
      <label class="field-label">Name</label>
      <input class="field-input" id="cf-name" required value="${c ? escapeAttr(c.name) : ''}">
      <div class="field-row">
        <div>
          <label class="field-label">Initials</label>
          <input class="field-input" id="cf-initials" maxlength="3" required value="${c ? escapeAttr(c.initials) : ''}">
        </div>
        <div>
          <label class="field-label">Status</label>
          <select class="field-select" id="cf-status">
            <option value="current" ${!c || c.status === 'current' ? 'selected' : ''}>Current</option>
            <option value="past" ${c && c.status === 'past' ? 'selected' : ''}>Past</option>
          </select>
        </div>
      </div>
      <label class="field-label">Next session</label>
      <input class="field-input" id="cf-next" placeholder="e.g. Thu, 6:00 PM - leave blank if none" value="${c && c.next_session ? escapeAttr(c.next_session) : ''}">
      <div class="field-row">
        <div>
          <label class="field-label">Sessions completed</label>
          <input class="field-input" id="cf-completed" type="number" min="0" value="${c ? c.sessions_completed : 0}">
        </div>
        <div>
          <label class="field-label">Sessions total</label>
          <input class="field-input" id="cf-total" type="number" min="0" value="${c ? c.sessions_total : 0}">
        </div>
      </div>
      <div class="field-row">
        <div>
          <label class="field-label">Amount paid ($)</label>
          <input class="field-input" id="cf-paid" type="number" min="0" step="0.01" value="${c ? c.amount_paid : 0}">
        </div>
        <div>
          <label class="field-label">Amount total ($)</label>
          <input class="field-input" id="cf-amount-total" type="number" min="0" step="0.01" value="${c ? c.amount_total : 0}">
        </div>
      </div>

      <div class="divider" style="margin:18px -22px;"></div>

      <label class="field-label" style="margin-top:0;">Email</label>
      <input class="field-input" type="email" id="cf-email" placeholder="Optional" value="${c && c.email ? escapeAttr(c.email) : ''}">
      <label class="field-label">Phone</label>
      <input class="field-input" type="tel" id="cf-phone" placeholder="Optional" value="${c && c.phone ? escapeAttr(c.phone) : ''}">
      <label class="field-label">Address</label>
      <input class="field-input" id="cf-address" placeholder="Optional" value="${c && c.address ? escapeAttr(c.address) : ''}">
      <label class="field-label">Location type</label>
      <input class="field-input" id="cf-location-type" placeholder="e.g. Client's Home, Studio Visit, Virtual" value="${c && c.location_type ? escapeAttr(c.location_type) : ''}">
      <label class="field-label">Start date</label>
      <input class="field-input" id="cf-start-date" placeholder="e.g. As soon as possible" value="${c && c.start_date ? escapeAttr(c.start_date) : ''}">
      <label class="field-label">Lessons per week</label>
      <input class="field-input" id="cf-lessons-per-week" type="number" min="0" value="${c && c.lessons_per_week != null ? c.lessons_per_week : ''}">
      <label class="field-label">Days available</label>
      <div id="cf-days" style="display:flex; flex-wrap:wrap; gap:6px; margin-top:4px;">
        ${DAY_ABBR.map((label, i) => `<button type="button" class="cd-day-chip ${selectedDays.includes(i) ? 'active' : ''}" data-day="${i}" onclick="this.classList.toggle('active')">${label}</button>`).join('')}
      </div>
      <div class="field-row" style="margin-top:12px;">
        <div>
          <label class="field-label">Weekday times</label>
          <div class="field-row">
            <input class="field-input" id="cf-weekday-start" type="time" value="${c && c.weekday_start ? c.weekday_start : ''}">
            <input class="field-input" id="cf-weekday-end" type="time" value="${c && c.weekday_end ? c.weekday_end : ''}">
          </div>
        </div>
      </div>
      <div class="field-row">
        <div>
          <label class="field-label">Weekend times</label>
          <div class="field-row">
            <input class="field-input" id="cf-weekend-start" type="time" value="${c && c.weekend_start ? c.weekend_start : ''}">
            <input class="field-input" id="cf-weekend-end" type="time" value="${c && c.weekend_end ? c.weekend_end : ''}">
          </div>
        </div>
      </div>

      <div id="cf-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">${isEdit ? 'Save Changes' : 'Add Client'}</button>
    </form>`;
  openModal(isEdit ? 'Edit Client' : 'Add Client', body);
}

async function submitClientForm(evt, id) {
  evt.preventDefault();
  const errorEl = document.getElementById('cf-error');
  errorEl.style.display = 'none';
  const name = document.getElementById('cf-name').value.trim();
  const initials = document.getElementById('cf-initials').value.trim().toUpperCase();
  if (!name || !initials) {
    errorEl.textContent = 'Name and initials are required.';
    errorEl.style.display = 'block';
    return;
  }
  const activeDays = Array.from(document.querySelectorAll('#cf-days .cd-day-chip.active')).map(b => b.dataset.day);
  const lessonsPerWeekRaw = document.getElementById('cf-lessons-per-week').value.trim();
  const payload = {
    name,
    initials,
    avatar_variant: (id && clientsCache[id]) ? clientsCache[id].avatar_variant : (Math.random() < 0.5 ? 'c1' : 'c2'),
    status: document.getElementById('cf-status').value,
    next_session: document.getElementById('cf-next').value.trim() || null,
    sessions_completed: Number(document.getElementById('cf-completed').value) || 0,
    sessions_total: Number(document.getElementById('cf-total').value) || 0,
    amount_paid: Number(document.getElementById('cf-paid').value) || 0,
    amount_total: Number(document.getElementById('cf-amount-total').value) || 0,
    email: document.getElementById('cf-email').value.trim() || null,
    phone: document.getElementById('cf-phone').value.trim() || null,
    address: document.getElementById('cf-address').value.trim() || null,
    location_type: document.getElementById('cf-location-type').value.trim() || null,
    start_date: document.getElementById('cf-start-date').value.trim() || null,
    lessons_per_week: lessonsPerWeekRaw ? Number(lessonsPerWeekRaw) : null,
    available_days: activeDays.length ? activeDays.join(',') : null,
    weekday_start: document.getElementById('cf-weekday-start').value || null,
    weekday_end: document.getElementById('cf-weekday-end').value || null,
    weekend_start: document.getElementById('cf-weekend-start').value || null,
    weekend_end: document.getElementById('cf-weekend-end').value || null,
  };
  try {
    if (id) {
      await apiFetch(`/api/clients/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await apiFetch('/api/clients', { method: 'POST', body: JSON.stringify(payload) });
    }
    closeModal();
    await Promise.all([loadClients('current'), loadClients('past'), loadSummary()]);
    if (id && currentClientDetailId === id) await openClientDetail(id);
  } catch (err) {
    errorEl.textContent = err.message || 'Could not save client.';
    errorEl.style.display = 'block';
  }
}

/* =========================================================
   CLIENT DETAIL
   ========================================================= */
let currentClientDetail = null;
let currentClientDetailId = null;

async function openClientDetail(id) {
  try {
    const c = await apiFetch(`/api/clients/${id}`);
    clientsCache[id] = c;
    currentClientDetail = c;
    currentClientDetailId = id;
    renderClientDetail(c);
    goToScreen('client-detail');
    loadClientRecurringIndicator(c.customer_id); // separate fetch, non-blocking — a hand-added client has no customer_id at all
  } catch (err) {
    alert(err.message || 'Could not load this client.');
  }
}

const RECURRING_DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

async function loadClientRecurringIndicator(customerId) {
  const el = document.getElementById('cd-recurring-block');
  el.innerHTML = '';
  if (!customerId) return;
  try {
    const series = await apiFetch('/api/recurring-series');
    const match = series.find(s => s.customer_id === customerId && s.status !== 'cancelled');
    if (!match) return;
    const statusNote = match.status === 'paused' ? ' (paused)' : '';
    el.innerHTML = `
      <div class="card" style="padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:4px;">
        <p class="client-name" style="font-size:14px; margin:0;">Recurring: every ${RECURRING_DAY_NAMES[match.day_of_week]}, ${match.start_time}${statusNote}</p>
        <button class="pill pill-outline" style="flex-shrink:0;" onclick="cancelHostedRecurringSeries(${match.id})">Stop Hosting</button>
      </div>`;
  } catch (err) {
    console.error('Failed to load recurring series for client:', err);
  }
}

async function cancelHostedRecurringSeries(seriesId) {
  if (!confirm("Stop hosting this client's standing weekly booking? No new lessons will be generated from it.")) return;
  try {
    await apiFetch(`/api/recurring-series/${seriesId}/cancel`, { method: 'PUT' });
    if (currentClientDetail) loadClientRecurringIndicator(currentClientDetail.customer_id);
  } catch (err) {
    alert(err.message || 'Could not stop this recurring booking.');
  }
}

function renderClientDetail(c) {
  document.getElementById('cd-avatar').textContent = escapeHtml(c.initials);
  document.getElementById('cd-avatar').className = `avatar avatar-sm avatar-${c.avatar_variant}`;
  document.getElementById('cd-name').textContent = c.name;
  document.getElementById('cd-id').textContent = `ID ${String(c.id).padStart(6, '0')}`;
  const badge = document.getElementById('cd-status-badge');
  badge.textContent = c.status === 'current' ? 'Matched' : 'Past';
  badge.classList.toggle('past', c.status !== 'current');

  document.getElementById('cd-total-pay').textContent = `$${c.amount_total}`;
  document.getElementById('cd-session-pack').textContent = `${c.sessions_total} session${c.sessions_total === 1 ? '' : 's'}`;
  const pct = c.sessions_total ? Math.round((c.sessions_completed / c.sessions_total) * 100) : 0;
  document.getElementById('cd-progress-fill').style.width = `${pct}%`;
  document.getElementById('cd-progress-text').innerHTML =
    `<b>${c.sessions_completed}</b> of ${c.sessions_total} sessions completed · <b>$${c.amount_paid}</b> of $${c.amount_total} paid`;
  const rateEl = document.getElementById('cd-per-session-rate');
  rateEl.textContent = c.sessions_total ? `Get paid $${(c.amount_total / c.sessions_total).toFixed(0)} per session` : '';

  const deleteBtn = document.getElementById('cd-delete-btn');
  deleteBtn.textContent = c.deletion_pending ? 'Pending' : 'Delete';
  deleteBtn.disabled = c.deletion_pending;
  deleteBtn.classList.toggle('pending', c.deletion_pending);

  // Report/Block only make sense for a client backed by a real Customer
  // account — a hand-added client (no customer_id) has no one to report.
  document.getElementById('cd-safety-row').style.display = c.customer_id ? 'flex' : 'none';
  if (c.customer_id) loadBlockedIndicator(c.customer_id);

  const contactEl = document.getElementById('cd-contact-block');
  if (c.email || c.phone) {
    contactEl.innerHTML = `
      ${c.email ? `<div class="cd-info-row"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg><p>${escapeHtml(c.email)}</p></div>` : ''}
      ${c.phone ? `<div class="cd-info-row"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3.1-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .3 2 .7 3a2 2 0 0 1-.4 2.1L8 10.2a16 16 0 0 0 6 6l1.4-1.4a2 2 0 0 1 2.1-.4c1 .4 2 .6 3 .7a2 2 0 0 1 1.7 2Z"/></svg><p>${escapeHtml(c.phone)}</p></div>` : ''}`;
  } else {
    contactEl.innerHTML = `<p class="empty-copy" style="text-align:left; margin:0; max-width:none;">No contact info on file yet.</p>`;
  }

  const locationEl = document.getElementById('cd-location-block');
  if (c.address || c.location_type) {
    locationEl.innerHTML = `
      ${c.address ? `<div class="cd-info-row"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12Z"/><circle cx="12" cy="9" r="2.4"/></svg><p>${escapeHtml(c.address)}</p></div>` : ''}
      ${c.location_type ? `<div class="cd-info-row"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11.5 12 4l8 7.5"/><path d="M6 10v9h12v-9"/></svg><p>${escapeHtml(c.location_type)}</p></div>` : ''}`;
  } else {
    locationEl.innerHTML = `<p class="empty-copy" style="text-align:left; margin:0; max-width:none;">No location on file yet.</p>`;
  }

  const availEl = document.getElementById('cd-availability-block');
  if (c.start_date || c.lessons_per_week || c.available_days || c.weekday_start || c.weekend_start) {
    const selectedDays = c.available_days ? c.available_days.split(',').map(Number) : [];
    const dayChips = DAY_ABBR.map((label, i) => `<span class="cd-day-chip ${selectedDays.includes(i) ? 'active' : ''}">${label}</span>`).join('');
    availEl.innerHTML = `
      <div class="card" style="padding:18px 20px;">
        <div class="field-row">
          <div><p class="next-label" style="text-align:left;">Start Date</p><p class="client-name" style="font-size:14px;">${c.start_date ? escapeHtml(c.start_date) : 'Not set'}</p></div>
          <div><p class="next-label" style="text-align:left;">Lessons / Week</p><p class="client-name" style="font-size:14px;">${c.lessons_per_week != null ? c.lessons_per_week + ' Lessons' : 'Not set'}</p></div>
        </div>
        <p class="next-label" style="text-align:left; margin-top:14px;">Days available</p>
        <div style="margin-top:6px;">${dayChips}</div>
        ${c.weekday_start ? `<p class="next-label" style="text-align:left; margin-top:14px;">Weekday times available</p><p class="client-name" style="font-size:14px;">${c.weekday_start} – ${c.weekday_end || '?'}</p>` : ''}
        ${c.weekend_start ? `<p class="next-label" style="text-align:left; margin-top:10px;">Weekend times available</p><p class="client-name" style="font-size:14px;">${c.weekend_start} – ${c.weekend_end || '?'}</p>` : ''}
      </div>`;
  } else {
    availEl.innerHTML = `<p class="empty-copy" style="text-align:left; margin:0; max-width:none;">No availability on file yet.</p>`;
  }

  const lessonsListEl = document.getElementById('cd-lessons-list');
  const lessonsEmptyEl = document.getElementById('cd-lessons-empty');
  if (c.lessons && c.lessons.length) {
    lessonsListEl.innerHTML = c.lessons.map(l => `
      <div class="cd-lesson-row">
        <div class="cd-lesson-badge">${l.lesson_number}</div>
        <div style="flex:1;">
          <p class="client-name" style="font-size:14px;">Lesson ${String(l.lesson_number).padStart(2, '0')}</p>
          <p class="${l.paid ? 'cd-lesson-paid' : 'cd-lesson-unpaid'}" style="cursor:pointer;" onclick="toggleLessonPaid(${l.id}, ${l.paid})" title="Click to mark as ${l.paid ? 'unpaid' : 'paid'}">${l.paid ? 'Paid' : 'Unpaid'}</p>
        </div>
        ${l.date ? `<p class="next-value" style="color:var(--brass);">${escapeHtml(l.date)}</p>` : ''}
        <button class="icon-btn" aria-label="Remove lesson" onclick="deleteClientLesson(${l.id})"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
      </div>`).join('');
    lessonsEmptyEl.style.display = 'none';
  } else {
    lessonsListEl.innerHTML = '';
    lessonsEmptyEl.style.display = 'block';
  }
}

function editClientFromDetail() {
  openClientForm(currentClientDetailId);
}

async function deleteClientFromDetail() {
  if (!currentClientDetailId) return;
  if (!confirm("Request deletion of this client? An admin needs to approve it before the client is actually removed.")) return;
  try {
    await apiFetch(`/api/clients/${currentClientDetailId}`, { method: 'DELETE' });
    await openClientDetail(currentClientDetailId); // stays on the page — the client isn't gone yet, just pending
  } catch (err) {
    alert(err.message || 'Could not request deletion.');
  }
}

function contactClient() {
  const c = currentClientDetail;
  if (c && c.email) {
    window.location.href = `mailto:${c.email}`;
  } else if (c && c.phone) {
    window.location.href = `tel:${c.phone}`;
  } else {
    alert('No contact info on file for this client yet.');
  }
}

/* =========================================================
   REPORT / BLOCK CLIENT
   Both only apply to a client backed by a real Customer account — see
   renderClientDetail's cd-safety-row visibility check above.
   ========================================================= */
let currentClientBlocked = false;

async function loadBlockedIndicator(customerId) {
  try {
    const blocked = await apiFetch('/api/profile/blocks');
    currentClientBlocked = blocked.some(b => b.client_id === currentClientDetailId);
    const btn = document.getElementById('cd-block-btn');
    btn.textContent = currentClientBlocked ? 'Unblock Client' : 'Block Client';
    btn.classList.toggle('pending', currentClientBlocked);
  } catch (err) {
    console.error('Failed to load block status:', err);
  }
}

function openReportClientModal() {
  const body = `
    <form id="report-client-form" onsubmit="submitReportClientForm(event)">
      <label class="field-label">Reason</label>
      <select class="field-select" id="rc-reason" required>
        <option value="">Select a reason</option>
        <option value="no-show">No-show</option>
        <option value="harassment">Harassment or inappropriate behavior</option>
        <option value="safety">Safety concern</option>
        <option value="other">Other</option>
      </select>
      <label class="field-label">Details (optional)</label>
      <textarea class="field-input" id="rc-message" style="min-height:80px;"></textarea>
      <div id="rc-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Submit Report</button>
    </form>`;
  openModal(`Report ${currentClientDetail ? currentClientDetail.name : 'Client'}`, body);
}

async function submitReportClientForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('rc-error');
  errorEl.style.display = 'none';
  const payload = {
    client_id: currentClientDetailId,
    reason: document.getElementById('rc-reason').value,
    message: document.getElementById('rc-message').value.trim() || null,
  };
  try {
    await apiFetch('/api/profile/reports', { method: 'POST', body: JSON.stringify(payload) });
    closeModal();
    alert('Report submitted. An admin will review it.');
  } catch (err) {
    errorEl.textContent = err.message || 'Could not submit report.';
    errorEl.style.display = 'block';
  }
}

async function toggleBlockClient() {
  const verb = currentClientBlocked ? 'unblock' : 'block';
  if (!confirm(`${verb === 'block' ? 'Block' : 'Unblock'} this client? ${verb === 'block' ? "You won't be matched with them again." : ''}`)) return;
  try {
    if (currentClientBlocked) {
      await apiFetch(`/api/profile/blocks/${currentClientDetailId}`, { method: 'DELETE' });
    } else {
      await apiFetch('/api/profile/blocks', { method: 'POST', body: JSON.stringify({ client_id: currentClientDetailId }) });
    }
    await openClientDetail(currentClientDetailId);
  } catch (err) {
    alert(err.message || `Could not ${verb} this client.`);
  }
}

function openAddLessonForm() {
  const nextNumber = currentClientDetail && currentClientDetail.lessons ? currentClientDetail.lessons.length + 1 : 1;
  const body = `
    <form id="lesson-form" onsubmit="submitAddLessonForm(event)">
      <label class="field-label">Lesson number</label>
      <input class="field-input" id="lf-number" type="number" min="1" required value="${nextNumber}">
      <label class="field-label">Date</label>
      <input class="field-input" id="lf-date" placeholder="e.g. 07/09/2026">
      <label style="display:flex; align-items:center; gap:8px; margin-top:14px; font-size:14px; cursor:pointer;">
        <input type="checkbox" id="lf-paid"> Paid
      </label>
      <div id="lf-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Add Lesson</button>
    </form>`;
  openModal('Add Lesson', body);
}

async function submitAddLessonForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('lf-error');
  errorEl.style.display = 'none';
  const payload = {
    lesson_number: Number(document.getElementById('lf-number').value) || 1,
    date: document.getElementById('lf-date').value.trim() || null,
    paid: document.getElementById('lf-paid').checked,
  };
  try {
    await apiFetch(`/api/clients/${currentClientDetailId}/lessons`, { method: 'POST', body: JSON.stringify(payload) });
    closeModal();
    await openClientDetail(currentClientDetailId);
  } catch (err) {
    errorEl.textContent = err.message || 'Could not add lesson.';
    errorEl.style.display = 'block';
  }
}

async function deleteClientLesson(lessonId) {
  if (!confirm('Remove this lesson entry?')) return;
  try {
    await apiFetch(`/api/clients/${currentClientDetailId}/lessons/${lessonId}`, { method: 'DELETE' });
    await openClientDetail(currentClientDetailId);
  } catch (err) {
    alert(err.message || 'Could not remove lesson.');
  }
}

async function toggleLessonPaid(lessonId, currentlyPaid) {
  try {
    await apiFetch(`/api/clients/${currentClientDetailId}/lessons/${lessonId}/paid`, {
      method: 'PUT', body: JSON.stringify({ paid: !currentlyPaid }),
    });
    await openClientDetail(currentClientDetailId);
  } catch (err) {
    alert(err.message || 'Could not update payment status.');
  }
}

/* =========================================================
   SESSIONS
   ========================================================= */
let sessionsCache = {};
let sessionFilterDays = [];
let sessionFilterMaxLessons = null;
let sessionSort = 'newest';

function sessionCardHTML(s) {
  sessionsCache[s.id] = s;
  const dayLabel = s.day_of_week != null ? DAY_ABBR[s.day_of_week] : null;
  const meta = [s.date, s.location, dayLabel, s.city].filter(Boolean).join(' · ');
  const actionBtn = s.status === 'open'
    ? `<button class="action-btn primary" onclick="requestSession(${s.id})">Request</button>`
    : `<button class="action-btn primary" onclick="withdrawSession(${s.id})">Withdraw</button>`;
  return `
    <div class="client-card">
      <div class="client-row">
        <div>
          <p class="client-name">${escapeHtml(s.title)}</p>
          <p class="client-id">${escapeHtml(meta)}</p>
        </div>
        <div><p class="next-value">${s.pay_rate ? escapeHtml(s.pay_rate) : ''}</p></div>
      </div>
      <div class="card-actions">
        ${actionBtn}
        <button class="action-btn" onclick="openSessionForm(${s.id})">Edit</button>
        <button class="action-btn danger" onclick="deleteSession(${s.id})">Delete</button>
      </div>
    </div>`;
}

async function loadSessions(status) {
  const listEl = document.getElementById(`sessions-${status}-list`);
  const emptyEl = document.getElementById(`sessions-${status}-empty`);
  try {
    const params = new URLSearchParams({ status });
    if (status === 'open') {
      sessionFilterDays.forEach(d => params.append('days', d));
      if (sessionFilterMaxLessons != null) params.set('max_lessons_per_week', sessionFilterMaxLessons);
      params.set('sort', sessionSort);
    }
    const data = await apiFetch(`/api/sessions?${params.toString()}`);
    if (data.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = data.map(sessionCardHTML).join('');
      emptyEl.style.display = 'none';
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.style.display = 'block';
    console.error('Failed to load sessions:', err);
  }
}

async function openSessionForm(id) {
  const s = id ? sessionsCache[id] : null;
  const isEdit = !!s;
  const cities = await loadCities();
  const body = `
    <form id="session-form" onsubmit="submitSessionForm(event, ${id || 'null'})">
      <label class="field-label">Title</label>
      <input class="field-input" id="sf-title" required value="${s ? escapeAttr(s.title) : ''}">
      <div class="field-row">
        <div>
          <label class="field-label">Date</label>
          <input class="field-input" id="sf-date" placeholder="e.g. Fri, 7:00 PM" value="${s && s.date ? escapeAttr(s.date) : ''}">
        </div>
        <div>
          <label class="field-label">Pay rate</label>
          <input class="field-input" id="sf-pay" placeholder="e.g. $60" value="${s && s.pay_rate ? escapeAttr(s.pay_rate) : ''}">
        </div>
      </div>
      <label class="field-label">Location</label>
      <input class="field-input" id="sf-location" value="${s && s.location ? escapeAttr(s.location) : ''}">
      <div class="field-row">
        <div>
          <label class="field-label">Day of week</label>
          <select class="field-select" id="sf-day">
            <option value="">Not set</option>
            ${DAY_ABBR.map((label, i) => `<option value="${i}" ${s && s.day_of_week === i ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="field-label">Lessons per week</label>
          <input class="field-input" id="sf-lessons-per-week" type="number" min="0" value="${s && s.lessons_per_week != null ? s.lessons_per_week : ''}">
        </div>
      </div>
      <label class="field-label">City</label>
      <select class="field-select" id="sf-city">
        <option value="">Not set</option>
        ${cities.map(c => `<option value="${c}" ${s && s.city === c ? 'selected' : ''}>${c}</option>`).join('')}
      </select>
      <label class="field-label">Notes</label>
      <textarea class="field-textarea" id="sf-notes">${s && s.notes ? escapeHtml(s.notes) : ''}</textarea>
      <div id="sf-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">${isEdit ? 'Save Changes' : 'Post Session'}</button>
    </form>`;
  openModal(isEdit ? 'Edit Session' : 'Add Session', body);
}

async function submitSessionForm(evt, id) {
  evt.preventDefault();
  const errorEl = document.getElementById('sf-error');
  errorEl.style.display = 'none';
  const title = document.getElementById('sf-title').value.trim();
  if (!title) {
    errorEl.textContent = 'Title is required.';
    errorEl.style.display = 'block';
    return;
  }
  const dayRaw = document.getElementById('sf-day').value;
  const lessonsRaw = document.getElementById('sf-lessons-per-week').value.trim();
  const payload = {
    title,
    status: (id && sessionsCache[id]) ? sessionsCache[id].status : 'open',
    date: document.getElementById('sf-date').value.trim() || null,
    location: document.getElementById('sf-location').value.trim() || null,
    pay_rate: document.getElementById('sf-pay').value.trim() || null,
    notes: document.getElementById('sf-notes').value.trim() || null,
    day_of_week: dayRaw ? Number(dayRaw) : null,
    lessons_per_week: lessonsRaw ? Number(lessonsRaw) : null,
    city: document.getElementById('sf-city').value || null,
  };
  try {
    if (id) {
      await apiFetch(`/api/sessions/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await apiFetch('/api/sessions', { method: 'POST', body: JSON.stringify(payload) });
    }
    closeModal();
    await Promise.all([loadSessions('open'), loadSessions('requested')]);
  } catch (err) {
    errorEl.textContent = err.message || 'Could not save session.';
    errorEl.style.display = 'block';
  }
}

function openSessionFilterModal() {
  const body = `
    <p class="field-label" style="margin-top:0;">Days Available</p>
    <div id="filter-days" style="display:flex; flex-wrap:wrap; gap:6px;">
      ${DAY_ABBR.map((label, i) => `<button type="button" class="cd-day-chip ${sessionFilterDays.includes(i) ? 'active' : ''}" data-day="${i}" onclick="this.classList.toggle('active')" style="width:auto; padding:0 12px;">${label}</button>`).join('')}
    </div>
    <p class="field-label">Max. lessons per week</p>
    <div id="filter-max-lessons" style="display:flex; flex-wrap:wrap; gap:6px;">
      ${[1, 2, 3, 4, 5, 6, 7].map(n => `<button type="button" class="cd-day-chip ${sessionFilterMaxLessons === n ? 'active' : ''}" data-max="${n}" onclick="selectFilterMaxLessons(${n}, this)" style="width:38px; border-radius:999px;">${n}</button>`).join('')}
    </div>
    <div style="display:flex; gap:10px; margin-top:20px;">
      <button type="button" class="pill pill-outline" style="flex:1;" onclick="clearSessionFilters()">Clear</button>
      <button type="button" class="pill pill-solid" style="flex:1;" onclick="applySessionFilters()">Apply Filters</button>
    </div>`;
  openModal('Filter by', body);
}

function selectFilterMaxLessons(n, btn) {
  const alreadyActive = btn.classList.contains('active');
  document.querySelectorAll('#filter-max-lessons .cd-day-chip').forEach(b => b.classList.remove('active'));
  if (!alreadyActive) btn.classList.add('active');
}

function clearSessionFilters() {
  sessionFilterDays = [];
  sessionFilterMaxLessons = null;
  closeModal();
  loadSessions('open');
}

async function applySessionFilters() {
  sessionFilterDays = Array.from(document.querySelectorAll('#filter-days .cd-day-chip.active')).map(b => Number(b.dataset.day));
  const activeMax = document.querySelector('#filter-max-lessons .cd-day-chip.active');
  sessionFilterMaxLessons = activeMax ? Number(activeMax.dataset.max) : null;
  closeModal();
  await loadSessions('open');
}

function openSessionSortModal() {
  const options = [
    { value: 'newest', label: 'Newest' },
    { value: 'nearest', label: 'Nearest' },
    { value: 'oldest', label: 'Oldest' },
    { value: 'farthest', label: 'Farthest' },
  ];
  const body = `
    <div id="sort-options">
      ${options.map(o => `
        <div class="list-row" data-sort="${o.value}" onclick="selectSortOption('${o.value}')" style="cursor:pointer;">
          <span style="flex:1;">${o.label}</span>
          <span class="sort-check" style="width:20px; height:20px; border-radius:999px; background:${sessionSort === o.value ? 'var(--plum)' : 'transparent'}; display:flex; align-items:center; justify-content:center; color:#fff; font-size:12px;">${sessionSort === o.value ? '✓' : ''}</span>
        </div>`).join('')}
    </div>
    <button type="button" class="pill pill-solid pill-block" style="width:100%; margin-top:20px;" onclick="applySessionSort()">Sort</button>`;
  openModal('Sort by', body);
}

let pendingSortSelection = null;

function selectSortOption(value) {
  pendingSortSelection = value;
  document.querySelectorAll('#sort-options .list-row').forEach(row => {
    const check = row.querySelector('.sort-check');
    const isSelected = row.dataset.sort === value;
    check.style.background = isSelected ? 'var(--plum)' : 'transparent';
    check.textContent = isSelected ? '✓' : '';
  });
}

async function applySessionSort() {
  sessionSort = pendingSortSelection || sessionSort;
  closeModal();
  await loadSessions('open');
}

async function deleteSession(id) {
  if (!confirm('Delete this session listing?')) return;
  try {
    await apiFetch(`/api/sessions/${id}`, { method: 'DELETE' });
    closeModal();
    await Promise.all([loadSessions('open'), loadSessions('requested')]);
  } catch (err) {
    alert(err.message || 'Could not delete session.');
  }
}

async function requestSession(id) {
  try {
    await apiFetch(`/api/sessions/${id}/request`, { method: 'PUT' });
    await Promise.all([loadSessions('open'), loadSessions('requested')]);
  } catch (err) {
    alert(err.message || 'Could not request this session.');
  }
}

async function withdrawSession(id) {
  try {
    await apiFetch(`/api/sessions/${id}/withdraw`, { method: 'PUT' });
    await Promise.all([loadSessions('open'), loadSessions('requested')]);
  } catch (err) {
    alert(err.message || 'Could not withdraw.');
  }
}

/* =========================================================
   CLIENT REQUESTS
   Pending package/scheduled-lesson requests broadcast to every
   instructor who matches (specialty, distance, and — for scheduled
   requests — availability overlap). Nothing here is "yours" until you
   confirm it: confirming is what charges the card and adds a real
   Client row.
   ========================================================= */
let clientRequestsCache = [];

function clientRequestCardHTML(r) {
  const specialtyLabel = r.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const scheduleLine = r.package
    ? `${r.package} package · ${r.sessions_total} session${r.sessions_total > 1 ? 's' : ''}`
    : `${DAY_NAMES[r.requested_day]}, ${r.requested_start_time}–${r.requested_end_time} · ${r.duration_minutes} min lesson`;
  const locationLine = [r.customer_city, r.distance_km != null ? `~${r.distance_km} km away` : null].filter(Boolean).join(' · ');
  const confirmPath = r.source === 'lesson_request' ? 'lesson-requests' : 'bookings';
  return `
    <div class="client-card">
      <div class="client-row">
        <div>
          <p class="client-name">${escapeHtml(r.customer_name)}</p>
          <p class="client-id">${escapeHtml(specialtyLabel)}</p>
        </div>
        <div><p class="next-value">$${r.amount_due}</p></div>
      </div>
      <p class="progress-text" style="margin-top:10px;">${escapeHtml(scheduleLine)}</p>
      ${locationLine ? `<p class="progress-text">${escapeHtml(locationLine)}</p>` : ''}
      ${r.notes ? `<p class="progress-text" style="font-style:italic; margin-top:6px;">“${escapeHtml(r.notes)}”</p>` : ''}
      <div class="card-actions">
        <button class="action-btn primary" onclick="confirmClientRequest('${confirmPath}', ${r.id})">Confirm Match</button>
      </div>
    </div>`;
}

async function loadClientRequests() {
  const listEl = document.getElementById('client-requests-list');
  const emptyEl = document.getElementById('client-requests-empty');
  try {
    clientRequestsCache = await apiFetch('/api/client-requests');
    if (clientRequestsCache.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = clientRequestsCache.map(clientRequestCardHTML).join('');
      emptyEl.style.display = 'none';
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.querySelector('.empty-copy').textContent = "Couldn't load client requests. Is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load client requests:', err);
  }
}

async function confirmClientRequest(type, id) {
  try {
    const confirmed = await apiFetch(`/api/client-requests/${type}/${id}/confirm`, { method: 'PUT' });
    await Promise.all([loadClientRequests(), loadClients('current'), loadClients('past'), loadSummary()]);
    alert(`You're matched with ${confirmed.customer_name}!\n\nEmail: ${confirmed.customer_email}\nPhone: ${confirmed.customer_phone}\n\n(Also saved on their Client Details page.)`);
  } catch (err) {
    alert(err.message || 'Could not confirm this match. It may have just been claimed by another instructor.');
    await loadClientRequests();
  }
}

/* =========================================================
   CLIENT REQUESTS MAP
   Leaflet, loaded via CDN (see index.html <head>) — no build step
   needed. Pins sit at each customer's demo-city coordinates.
   ========================================================= */
let clientRequestsMapInstance = null;

function openClientRequestsMap() {
  const body = `<div id="client-requests-map" style="height:360px; border-radius:16px; overflow:hidden;"></div>
    <p class="empty-copy" style="margin-top:14px;">Pins show pending client requests currently visible to you. Tap one for the pay and specialty.</p>`;
  openModal('Client Requests Map', body);

  const pins = clientRequestsCache.filter(r => r.customer_lat != null && r.customer_lng != null);

  setTimeout(() => {
    if (clientRequestsMapInstance) {
      clientRequestsMapInstance.remove();
      clientRequestsMapInstance = null;
    }
    const map = L.map('client-requests-map');
    clientRequestsMapInstance = map;
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);

    if (pins.length === 0) {
      map.setView([39.8, -98.6], 4); // continental US, nothing to fit to
      return;
    }
    const markers = pins.map(r => {
      const specialtyLabel = r.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';
      return L.marker([r.customer_lat, r.customer_lng])
        .bindPopup(`<b>${escapeHtml(r.customer_name)}</b><br>${escapeHtml(specialtyLabel)} · $${r.amount_due}`);
    });
    const group = L.featureGroup(markers).addTo(map);
    map.fitBounds(group.getBounds(), { padding: [40, 40], maxZoom: 10 });
  }, 50); // modal DOM needs to exist (and be visible) before Leaflet can measure it
}

/* =========================================================
   PROFILE
   ========================================================= */
let profileCache = null;

async function loadProfile() {
  try {
    const p = await apiFetch('/api/profile');
    profileCache = p;
    document.getElementById('profile-name').textContent = p.name;
    document.getElementById('profile-bio').textContent = p.bio || 'Add a short bio so clients know who you are.';
    document.getElementById('profile-initials').textContent = initialsFromName(p.name);
    document.getElementById('profile-email').textContent = p.email;
    document.getElementById('active-toggle').classList.toggle('on', !!p.active);

    const labels = { yoga: 'Yoga', sound_bath: 'Sound Bath' };
    const specialties = (p.specialty || '').split(',').map(s => s.trim()).filter(Boolean);
    document.getElementById('profile-specialty-badges').innerHTML = specialties
      .map(s => `<span class="specialty-pill">${labels[s] || s}</span>`).join('');

    document.getElementById('max-distance-input').value = p.max_travel_distance_km != null ? p.max_travel_distance_km : '';

    document.getElementById('profile-rating-summary').textContent = p.review_count > 0
      ? `★ ${p.average_rating.toFixed(1)} (${p.review_count} review${p.review_count > 1 ? 's' : ''})`
      : 'No reviews yet';
  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

async function saveMaxDistance() {
  const raw = document.getElementById('max-distance-input').value.trim();
  const max_travel_distance_km = raw === '' ? null : Number(raw);
  try {
    await apiFetch('/api/profile', { method: 'PUT', body: JSON.stringify({ max_travel_distance_km }) });
    if (profileCache) profileCache.max_travel_distance_km = max_travel_distance_km;
    await loadClientRequests();
  } catch (err) {
    alert(err.message || 'Could not save travel distance.');
  }
}

let citiesCache = [];
async function loadCities() {
  if (citiesCache.length) return citiesCache;
  try {
    citiesCache = await apiFetch('/api/cities');
  } catch (err) {
    console.error('Failed to load cities:', err);
  }
  return citiesCache;
}

async function openProfileForm() {
  const p = profileCache || {};
  const specialties = (p.specialty || '').split(',').map(s => s.trim());
  const body = `
    <form id="profile-form" onsubmit="submitProfileForm(event)">
      <label class="field-label">Name</label>
      <input class="field-input" id="pf-name" required value="${escapeAttr(p.name || '')}">
      <label class="field-label">Phone</label>
      <input class="field-input" type="tel" id="pf-phone" value="${escapeAttr(p.phone || '')}">
      <label class="field-label">Bio</label>
      <textarea class="field-textarea" id="pf-bio">${escapeHtml(p.bio || '')}</textarea>
      <label class="field-label">Address</label>
      <input class="field-input" id="pf-address" value="${escapeAttr(p.address || '')}">
      <label class="field-label">City / State <span style="font-weight:400; text-transform:none; letter-spacing:0;">(used for scheduled-lesson matching)</span></label>
      <div class="field-row">
        <div>
          <input class="field-input" id="pf-city" placeholder="City" value="${escapeAttr(p.city_name || '')}">
        </div>
        <div>
          <input class="field-input" id="pf-state" placeholder="State" value="${escapeAttr(p.state_name || '')}">
        </div>
      </div>
      <label class="field-label">Certifications</label>
      <input class="field-input" id="pf-certs" placeholder="Comma-separated, e.g. RYT-500, Sound Healing" value="${escapeAttr(p.certifications || '')}">
      <label class="field-label">Specialty (used to match new customers to you)</label>
      <div style="display:flex; gap:16px; margin-top:4px;">
        <label style="display:flex; align-items:center; gap:6px; font-size:14px; cursor:pointer;">
          <input type="checkbox" id="pf-spec-yoga" ${specialties.includes('yoga') ? 'checked' : ''}> Yoga
        </label>
        <label style="display:flex; align-items:center; gap:6px; font-size:14px; cursor:pointer;">
          <input type="checkbox" id="pf-spec-sound" ${specialties.includes('sound_bath') ? 'checked' : ''}> Sound Bath
        </label>
      </div>
      <div id="pf-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Save Profile</button>
    </form>`;
  openModal('Edit Profile', body);
}

async function submitProfileForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('pf-error');
  errorEl.style.display = 'none';
  const name = document.getElementById('pf-name').value.trim();
  if (!name) {
    errorEl.textContent = 'Name is required.';
    errorEl.style.display = 'block';
    return;
  }
  const specialties = [];
  if (document.getElementById('pf-spec-yoga').checked) specialties.push('yoga');
  if (document.getElementById('pf-spec-sound').checked) specialties.push('sound_bath');
  if (specialties.length === 0) {
    errorEl.textContent = 'Select at least one specialty so customers can be matched to you.';
    errorEl.style.display = 'block';
    return;
  }
  const cityVal = document.getElementById('pf-city').value.trim();
  const stateVal = document.getElementById('pf-state').value.trim();
  if ((cityVal && !stateVal) || (!cityVal && stateVal)) {
    errorEl.textContent = 'Enter both city and state, or leave both blank.';
    errorEl.style.display = 'block';
    return;
  }
  const payload = {
    name,
    phone: document.getElementById('pf-phone').value.trim(),
    bio: document.getElementById('pf-bio').value.trim(),
    address: document.getElementById('pf-address').value.trim(),
    certifications: document.getElementById('pf-certs').value.trim(),
    specialty: specialties.join(','),
  };
  if (cityVal && stateVal) {
    payload.city_name = cityVal;
    payload.state_name = stateVal;
  }
  try {
    await apiFetch('/api/profile', { method: 'PUT', body: JSON.stringify(payload) });
    closeModal();
    await Promise.all([loadProfile(), loadSummary()]);
  } catch (err) {
    errorEl.textContent = err.message || 'Could not save profile.';
    errorEl.style.display = 'block';
  }
}

async function toggleActiveProfile() {
  const toggle = document.getElementById('active-toggle');
  const newState = !toggle.classList.contains('on');
  toggle.classList.toggle('on', newState); // optimistic — flips instantly, reverted below on failure
  try {
    await apiFetch('/api/profile', { method: 'PUT', body: JSON.stringify({ active: newState }) });
    if (profileCache) profileCache.active = newState;
  } catch (err) {
    toggle.classList.toggle('on', !newState);
    alert(err.message || 'Could not update your active status.');
  }
}

/* =========================================================
   NOTIFICATION SETTINGS
   A single on/off switch, not per-notification-type granularity — same
   shape as the Active Profile toggle above, just reached through its
   own modal instead of a home-screen row.
   ========================================================= */
function openNotificationSettingsModal() {
  const p = profileCache || {};
  const body = `
    <div class="list-row" style="cursor:default;">
      <span>Email me about new matches, reviews, and account updates</span>
      <div class="toggle ${p.email_notifications !== false ? 'on' : ''}" id="notif-toggle" onclick="toggleEmailNotifications()"></div>
    </div>`;
  openModal('Notification Settings', body);
}

async function toggleEmailNotifications() {
  const toggle = document.getElementById('notif-toggle');
  const newState = !toggle.classList.contains('on');
  toggle.classList.toggle('on', newState);
  try {
    await apiFetch('/api/profile', { method: 'PUT', body: JSON.stringify({ email_notifications: newState }) });
    if (profileCache) profileCache.email_notifications = newState;
  } catch (err) {
    toggle.classList.toggle('on', !newState);
    alert(err.message || 'Could not update notification settings.');
  }
}

/* =========================================================
   CHANGE PASSWORD
   Distinct from the Forgot Password flow (auth screen, logged out) —
   this is for someone already logged in who knows their current
   password and wants to set a new one.
   ========================================================= */
function openChangePasswordModal() {
  const body = `
    <form id="change-password-form" onsubmit="submitChangePasswordForm(event)">
      <label class="field-label">Current password</label>
      <input class="field-input" type="password" id="cp-current" required>
      <label class="field-label">New password</label>
      <input class="field-input" type="password" id="cp-new" required minlength="8">
      <div id="cp-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <div id="cp-success" style="display:none; margin-top:12px; color:var(--sage-dark, #4a6a5a);">Password updated.</div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Update Password</button>
    </form>`;
  openModal('Change Password', body);
}

async function submitChangePasswordForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('cp-error');
  const successEl = document.getElementById('cp-success');
  errorEl.style.display = 'none';
  successEl.style.display = 'none';
  try {
    await apiFetch('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: document.getElementById('cp-current').value,
        new_password: document.getElementById('cp-new').value,
      }),
    });
    document.getElementById('change-password-form').reset();
    successEl.style.display = 'block';
  } catch (err) {
    errorEl.textContent = err.message || 'Could not update password.';
    errorEl.style.display = 'block';
  }
}

/* =========================================================
   AVAILABILITY (Session Preferences)
   ========================================================= */
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
let availabilityCache = {};

function availabilityRowHTML(b) {
  availabilityCache[b.id] = b;
  return `
    <div class="client-card">
      <div class="client-row">
        <div>
          <p class="client-name">${DAY_NAMES[b.day_of_week]}</p>
          <p class="client-id">${escapeHtml(b.start_time)} – ${escapeHtml(b.end_time)}</p>
        </div>
      </div>
      <div class="card-actions">
        <button class="action-btn danger" onclick="deleteAvailability(${b.id})">Remove</button>
      </div>
    </div>`;
}

async function loadAvailability() {
  const listEl = document.getElementById('availability-list');
  const emptyEl = document.getElementById('availability-empty');
  try {
    const data = await apiFetch('/api/availability');
    if (data.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = data.map(availabilityRowHTML).join('');
      emptyEl.style.display = 'none';
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.querySelector('.empty-copy').textContent = "Couldn't load availability. Is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load availability:', err);
  }
}

function openAvailabilityForm() {
  const body = `
    <form id="availability-form" onsubmit="submitAvailabilityForm(event)">
      <label class="field-label">Day</label>
      <select class="field-select" id="af-day">
        ${DAY_NAMES.map((d, i) => `<option value="${i}">${d}</option>`).join('')}
      </select>
      <div class="field-row">
        <div>
          <label class="field-label">Start time</label>
          <input class="field-input" id="af-start" type="time" required value="09:00">
        </div>
        <div>
          <label class="field-label">End time</label>
          <input class="field-input" id="af-end" type="time" required value="11:00">
        </div>
      </div>
      <div id="af-error" class="form-error" style="display:none; margin-top:12px;"></div>
      <button class="pill pill-solid pill-block" type="submit" style="margin-top:16px;">Add Availability</button>
    </form>`;
  openModal('Add Availability', body);
}

async function submitAvailabilityForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('af-error');
  errorEl.style.display = 'none';
  const payload = {
    day_of_week: Number(document.getElementById('af-day').value),
    start_time: document.getElementById('af-start').value,
    end_time: document.getElementById('af-end').value,
  };
  try {
    await apiFetch('/api/availability', { method: 'POST', body: JSON.stringify(payload) });
    closeModal();
    await loadAvailability();
  } catch (err) {
    errorEl.textContent = err.message || 'Could not add availability.';
    errorEl.style.display = 'block';
  }
}

async function deleteAvailability(id) {
  if (!confirm('Remove this availability window?')) return;
  try {
    await apiFetch(`/api/availability/${id}`, { method: 'DELETE' });
    await loadAvailability();
  } catch (err) {
    alert(err.message || 'Could not remove availability.');
  }
}

/* =========================================================
   LEARN / FAQ
   ========================================================= */
async function loadFaqs(category) {
  const listEl = document.getElementById('faq-list');
  try {
    const query = category && category !== 'all' ? `?category=${encodeURIComponent(category)}` : '';
    const data = await apiFetch(`/api/faqs${query}`);
    listEl.innerHTML = data.length
      ? data.map(f => `<div class="faq-card">${escapeHtml(f.question)}</div>`).join('')
      : `<p class="empty-copy" style="margin-top:30px;">No FAQs in this category yet.</p>`;
    filterFaqs(); // keep an active search applied across a category switch
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy" style="margin-top:30px;">Couldn't load FAQs. Is the backend running?</p>`;
    console.error('Failed to load FAQs:', err);
  }
}

function filterFaqs() {
  const q = document.getElementById('faq-search-input').value.trim().toLowerCase();
  document.querySelectorAll('#faq-list .faq-card').forEach(card => {
    card.style.display = card.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

function setFaqCategory(el, category) {
  el.parentElement.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  loadFaqs(category);
}

/* =========================================================
   BOOT
   ========================================================= */
async function loadMyReviews() {
  const listEl = document.getElementById('reviews-list');
  const emptyEl = document.getElementById('reviews-empty');
  const summaryEl = document.getElementById('reviews-summary');
  try {
    const reviews = await apiFetch('/api/profile/reviews');
    if (reviews.length === 0) {
      listEl.innerHTML = '';
      summaryEl.textContent = '';
      emptyEl.style.display = 'block';
      return;
    }
    emptyEl.style.display = 'none';
    const avg = reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length;
    summaryEl.textContent = `★ ${avg.toFixed(1)} · ${reviews.length} review${reviews.length > 1 ? 's' : ''}`;
    listEl.innerHTML = reviews.map(r => `
      <div class="review-card">
        <div class="review-stars">${'★'.repeat(r.rating)}${'☆'.repeat(5 - r.rating)}</div>
        ${r.comment ? `<p class="review-comment">"${escapeHtml(r.comment)}"</p>` : ''}
        <p class="review-meta">${escapeHtml(r.customer_name || 'A customer')} · ${new Date(r.created_at).toLocaleDateString()}</p>
      </div>`).join('');
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.querySelector('.empty-copy').textContent = "Couldn't load reviews. Is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load reviews:', err);
  }
}

async function boot() {
  if (!getToken()) {
    document.getElementById('login-screen').classList.remove('hidden');
    return;
  }
  document.getElementById('login-screen').classList.add('hidden');
  await Promise.all([
    loadSummary(),
    loadClients('current'),
    loadClients('past'),
    loadSessions('open'),
    loadSessions('requested'),
    loadProfile(),
    loadFaqs('all'),
    loadAvailability(),
    loadClientRequests(),
    loadMyReviews(),
  ]);
}

document.addEventListener('DOMContentLoaded', () => {
  const resetToken = new URLSearchParams(window.location.search).get('reset_token');
  if (resetToken) {
    history.replaceState(null, '', window.location.pathname);
    openResetPasswordModal(resetToken);
  }
  boot();
  initGoogleSignIn();
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}
