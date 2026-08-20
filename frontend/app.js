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
  document.getElementById('auth-name').required = isSignup;
  document.getElementById('login-sub').textContent = isSignup ? "Create your instructor account" : "Log in to your instructor account";
  document.getElementById('auth-submit-btn').textContent = isSignup ? 'Create Account' : 'Log In';
  document.getElementById('auth-toggle-btn').textContent = isSignup ? 'Already have an account? Log in' : 'New here? Create an account';
  document.getElementById('login-error').style.display = 'none';
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
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
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
    <div class="client-card">
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
      <div class="card-actions">
        <button class="action-btn" onclick="openClientForm(${c.id})">Edit</button>
        <button class="action-btn danger" onclick="deleteClient(${c.id})">Delete</button>
      </div>
    </div>`;
}

async function loadClients(status) {
  const listEl = document.getElementById(`clients-${status}-list`);
  const emptyEl = document.getElementById(`clients-${status}-empty`);
  try {
    const data = await apiFetch(`/api/clients?status=${status}`);
    if (data.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = data.map(clientCardHTML).join('');
      emptyEl.style.display = 'none';
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.querySelector('.empty-copy').textContent = "Couldn't load clients — is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load clients:', err);
  }
}

function openClientForm(id) {
  const c = id ? clientsCache[id] : null;
  const isEdit = !!c;
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
      <input class="field-input" id="cf-next" placeholder="e.g. Thu, 6:00 PM — leave blank if none" value="${c && c.next_session ? escapeAttr(c.next_session) : ''}">
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
  };
  try {
    if (id) {
      await apiFetch(`/api/clients/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await apiFetch('/api/clients', { method: 'POST', body: JSON.stringify(payload) });
    }
    closeModal();
    await Promise.all([loadClients('current'), loadClients('past'), loadSummary()]);
  } catch (err) {
    errorEl.textContent = err.message || 'Could not save client.';
    errorEl.style.display = 'block';
  }
}

async function deleteClient(id) {
  if (!confirm("Delete this client? This can't be undone.")) return;
  try {
    await apiFetch(`/api/clients/${id}`, { method: 'DELETE' });
    closeModal();
    await Promise.all([loadClients('current'), loadClients('past'), loadSummary()]);
  } catch (err) {
    alert(err.message || 'Could not delete client.');
  }
}

/* =========================================================
   SESSIONS
   ========================================================= */
let sessionsCache = {};

function sessionCardHTML(s) {
  sessionsCache[s.id] = s;
  const meta = [s.date, s.location].filter(Boolean).join(' · ');
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
    const data = await apiFetch(`/api/sessions?status=${status}`);
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

function openSessionForm(id) {
  const s = id ? sessionsCache[id] : null;
  const isEdit = !!s;
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
  const payload = {
    title,
    status: (id && sessionsCache[id]) ? sessionsCache[id].status : 'open',
    date: document.getElementById('sf-date').value.trim() || null,
    location: document.getElementById('sf-location').value.trim() || null,
    pay_rate: document.getElementById('sf-pay').value.trim() || null,
    notes: document.getElementById('sf-notes').value.trim() || null,
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
  } catch (err) {
    console.error('Failed to load profile:', err);
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
  const cities = await loadCities();
  const body = `
    <form id="profile-form" onsubmit="submitProfileForm(event)">
      <label class="field-label">Name</label>
      <input class="field-input" id="pf-name" required value="${escapeAttr(p.name || '')}">
      <label class="field-label">Bio</label>
      <textarea class="field-textarea" id="pf-bio">${escapeHtml(p.bio || '')}</textarea>
      <label class="field-label">Address</label>
      <input class="field-input" id="pf-address" value="${escapeAttr(p.address || '')}">
      <label class="field-label">City (used for scheduled-lesson matching)</label>
      <select class="field-select" id="pf-city">
        <option value="">Not set</option>
        ${cities.map(c => `<option value="${escapeAttr(c)}" ${p.city === c ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}
      </select>
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
  const payload = {
    name,
    bio: document.getElementById('pf-bio').value.trim(),
    address: document.getElementById('pf-address').value.trim(),
    certifications: document.getElementById('pf-certs').value.trim(),
    specialty: specialties.join(','),
  };
  const cityVal = document.getElementById('pf-city').value;
  if (cityVal) payload.city = cityVal; // omit entirely when "Not set" — an empty string isn't a valid city
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
    emptyEl.querySelector('.empty-copy').textContent = "Couldn't load availability — is the backend running?";
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
  } catch (err) {
    listEl.innerHTML = `<p class="empty-copy" style="margin-top:30px;">Couldn't load FAQs — is the backend running?</p>`;
    console.error('Failed to load FAQs:', err);
  }
}

function setFaqCategory(el, category) {
  el.parentElement.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  loadFaqs(category);
}

/* =========================================================
   BOOT
   ========================================================= */
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
  ]);
}

document.addEventListener('DOMContentLoaded', boot);
