/* =========================================================
   NAVIGATION
   ========================================================= */
function goToScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  window.scrollTo(0, 0);
}
function goHome() {
  goToScreen('landing');
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* =========================================================
   AUTH
   Uses its own localStorage key (attune_customer_token) so this
   app's session never collides with the instructor app's token,
   even though both are served from the same origin.
   ========================================================= */
const TOKEN_KEY = 'attune_customer_token';
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

let authMode = 'login';
let selectedSpecialty = null;
let selectedPackage = null;
let packageCatalog = {};

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
// 2-hour windows spanning 6am-10pm.
const TIME_WINDOWS = [
  { label: '6–8am', start: '06:00', end: '08:00' },
  { label: '8–10am', start: '08:00', end: '10:00' },
  { label: '10am–12pm', start: '10:00', end: '12:00' },
  { label: '12–2pm', start: '12:00', end: '14:00' },
  { label: '2–4pm', start: '14:00', end: '16:00' },
  { label: '4–6pm', start: '16:00', end: '18:00' },
  { label: '6–8pm', start: '18:00', end: '20:00' },
  { label: '8–10pm', start: '20:00', end: '22:00' },
];
let selectedWindows = []; // [{day_of_week, start_time, end_time}, ...] — built up on the availability screen
let selectedDuration = null;
let selectedLessonsPerWeek = null; // a stated preference, not enforced — see models.LessonRequest
let durationCatalog = {};
let lastRequestType = null; // 'package' | 'schedule' — which /me endpoint checkLatestStatus() re-polls
let lastRequestId = null; // id of whatever renderMatch() last drew — set in renderMatch itself, read by cancelCurrentRequest
let preferredInstructorId = null; // set by "Book Again with [Name]", sent as-is in the final submit payload
let preferredInstructorName = null; // display-only echo of the above, never sent to the backend
let blockedInstructorIds = new Set(); // populated by loadHistory(), read by historyCardHTML
let reviewsByKey = {}; // populated by loadHistory(), keyed like historyCardHTML's `key` — read by historyCardHTML/toggleReviewForm

function showAuth(mode) {
  authMode = mode;
  applyAuthMode();
  goToScreen('auth');
}

function toggleAuthMode() {
  authMode = authMode === 'login' ? 'signup' : 'login';
  applyAuthMode();
}

function applyAuthMode() {
  const isSignup = authMode === 'signup';
  document.getElementById('signup-name-field').style.display = isSignup ? 'block' : 'none';
  document.getElementById('auth-email-note').style.display = isSignup ? 'inline' : 'none';
  document.getElementById('auth-name').required = isSignup;
  document.getElementById('auth-phone').required = isSignup;
  document.getElementById('auth-title').textContent = isSignup ? 'Create Your Account' : 'Log In';
  document.getElementById('auth-sub').textContent = isSignup ? 'Takes about a minute.' : 'Welcome back.';
  document.getElementById('auth-submit-btn').textContent = isSignup ? 'Create Account' : 'Log In';
  document.getElementById('auth-toggle-btn').textContent = isSignup ? 'Already have an account? Log in' : 'New here? Create an account';
  document.getElementById('forgot-password-btn').style.display = isSignup ? 'none' : 'block';
  document.getElementById('auth-error').style.display = 'none';
}

/* =========================================================
   FORGOT / RESET PASSWORD
   Unauthenticated, so plain fetch (not apiFetch) — same reasoning as
   the instructor app's version of these two functions.
   ========================================================= */
let pendingResetToken = null;

async function submitForgotPasswordForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('fp-error');
  const successEl = document.getElementById('fp-success');
  errorEl.style.display = 'none';
  const email = document.getElementById('fp-email').value.trim();
  try {
    const res = await fetch('/api/customer/auth/forgot-password', {
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

async function submitResetPasswordForm(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('rp-error');
  errorEl.style.display = 'none';
  const newPassword = document.getElementById('rp-password').value;
  try {
    const res = await fetch('/api/customer/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: pendingResetToken, new_password: newPassword }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'That reset link is invalid or has expired.');
    goToScreen('auth');
    document.getElementById('auth-error').textContent = 'Password updated. Log in with your new password.';
    document.getElementById('auth-error').style.display = 'block';
  } catch (err) {
    errorEl.textContent = err.message || 'That reset link is invalid or has expired.';
    errorEl.style.display = 'block';
  }
}

async function handleAuthSubmit(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('auth-error');
  errorEl.style.display = 'none';
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;

  try {
    let token;
    if (authMode === 'signup') {
      const name = document.getElementById('auth-name').value.trim();
      const phone = document.getElementById('auth-phone').value.trim();
      const res = await fetch('/api/customer/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, phone, password }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not sign up');
      token = (await res.json()).access_token;
      setToken(token);
      updateNav();
      await goToSpecialtyStep();
    } else {
      const form = new URLSearchParams();
      form.set('username', email);
      form.set('password', password);
      const res = await fetch('/api/customer/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Incorrect email or password');
      token = (await res.json()).access_token;
      setToken(token);
      updateNav();
      await routeLoggedInCustomer();
    }
  } catch (err) {
    errorEl.textContent = err.message || 'Something went wrong.';
    errorEl.style.display = 'block';
  }
}

function logout() {
  clearToken();
  updateNav();
  goHome();
}

/* =========================================================
   GOOGLE SIGN-IN
   Only renders a button if the backend reports a configured
   GOOGLE_CLIENT_ID (see main.py's GET /api/config) — a deployment with
   no client ID set just shows the normal email/password form, not a
   broken button.
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
  const errorEl = document.getElementById('auth-error');
  errorEl.style.display = 'none';
  try {
    const res = await fetch('/api/customer/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: response.credential }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not sign in with Google.');
    setToken((await res.json()).access_token);
    updateNav();
    await routeLoggedInCustomer();
  } catch (err) {
    errorEl.textContent = err.message || 'Something went wrong.';
    errorEl.style.display = 'block';
  }
}

function updateNav() {
  const loggedIn = !!getToken();
  document.getElementById('nav-login-btn').style.display = loggedIn ? 'none' : 'inline-block';
  document.getElementById('nav-logout-btn').style.display = loggedIn ? 'inline-block' : 'none';
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
    clearToken();
    updateNav();
    goHome();
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
   WIZARD: specialty -> availability -> package -> payment -> match
   ========================================================= */
async function goToSpecialtyStep() {
  goToScreen('specialty');
}

async function selectSpecialty(specialty) {
  preferredInstructorId = null; // a fresh specialty pick always means a regular (broadcast) request
  preferredInstructorName = null;
  selectedSpecialty = specialty;
  await initAvailabilityStep();
  goToScreen('availability');
}

/* Rebooking — "Book Again with [Name]" on a matched History card. Skips
   straight to the availability step the normal wizard would only reach
   after picking a specialty, since that's already implied by the past
   match being rebooked. */
async function rebookRequest(instructorId, specialty, encodedInstructorName) {
  preferredInstructorId = instructorId;
  preferredInstructorName = decodeURIComponent(encodedInstructorName || '');
  selectedSpecialty = specialty;
  await initAvailabilityStep();
  goToScreen('availability');
}

/* Prices are duration-scaled (see estimatedPackagePrice below) and
   duration is always picked on the availability step, which now runs
   before this one — so by the time a customer sees package prices,
   they're the real total for the lesson length already chosen, not a
   30-min baseline placeholder. */
async function loadPackages() {
  const listEl = document.getElementById('package-list');
  listEl.innerHTML = '<p class="card-sub">Loading packages…</p>';
  try {
    packageCatalog = await apiFetch('/api/customer/bookings/packages');
    const labels = { single: 'Single Session', pack4: '4-Session Package', pack8: '8-Session Package', pack12: '12-Session Package', pack16: '16-Session Package' };
    listEl.innerHTML = Object.entries(packageCatalog).map(([key, info]) => {
      const total = estimatedPackagePrice(key, selectedDuration);
      const perSession = Math.round(total / info.sessions);
      return `
        <button class="package-card" onclick="selectPackage('${key}')">
          <div>
            <p class="package-name">${labels[key] || key}</p>
            <p class="package-meta">${info.sessions} session${info.sessions > 1 ? 's' : ''} · $${perSession}/session</p>
          </div>
          <p class="package-price">$${total}</p>
        </button>`;
    }).join('');
  } catch (err) {
    listEl.innerHTML = `<p class="form-error">Couldn't load packages. Is the backend running?</p>`;
    console.error(err);
  }
}

function selectPackage(pkg) {
  selectedPackage = pkg;
  const info = packageCatalog[pkg];
  const specialtyLabel = selectedSpecialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const rebookNote = preferredInstructorId ? ` · Booking again with ${preferredInstructorName}` : '';
  const lessonsPerWeekNote = selectedLessonsPerWeek ? ` · ${selectedLessonsPerWeek}/week` : '';
  const price = estimatedPackagePrice(pkg, selectedDuration);
  document.getElementById('payment-summary').textContent =
    `${specialtyLabel} · ${info.sessions} session${info.sessions > 1 ? 's' : ''} · ${selectedDuration} min · ${selectedWindows.length} window${selectedWindows.length > 1 ? 's' : ''} submitted${lessonsPerWeekNote} · $${price}${rebookNote}`;
  goToScreen('payment');
}

/* =========================================================
   WIZARD: availability (duration + multiple day/window picks + address)
   ========================================================= */
async function loadDurations() {
  if (Object.keys(durationCatalog).length) return durationCatalog;
  try {
    durationCatalog = await apiFetch('/api/customer/lesson-requests/durations');
  } catch (err) {
    console.error('Failed to load durations:', err);
  }
  return durationCatalog;
}

async function initAvailabilityStep() {
  selectedWindows = [];
  selectedDuration = null;
  selectedAvailDays = new Set();
  selectedAvailWindowIndices = new Set();

  const durations = await loadDurations();
  const durationEl = document.getElementById('avail-duration-picker');
  durationEl.innerHTML = Object.entries(durations).map(([minutes, price]) =>
    `<button type="button" class="window-btn" data-duration="${minutes}" onclick="selectAvailDuration(${minutes})">${minutes} min · $${price}</button>`
  ).join('');

  const dayEl = document.getElementById('avail-day-picker');
  dayEl.innerHTML = DAY_NAMES.map((name, i) =>
    `<button type="button" class="day-btn" data-day="${i}" onclick="toggleAvailDay(${i})">${name.slice(0, 3)}</button>`
  ).join('');

  const windowEl = document.getElementById('avail-window-picker');
  windowEl.innerHTML = TIME_WINDOWS.map((w, i) =>
    `<button type="button" class="window-btn" data-window="${i}" onclick="toggleAvailWindow(${i})">${w.label}</button>`
  ).join('');

  document.getElementById('avail-lessons-per-week').value = '';
  document.getElementById('avail-address').value = '';
  document.getElementById('avail-city').value = '';
  document.getElementById('avail-state').value = '';
}

// Multi-select, no separate "add" step: a day/window button toggles its
// own highlight and that's the selection, directly — no staging area, no
// confirmation chip list. The actual submitted windows are the full cross
// product (every selected day paired with every selected window),
// computed once in submitAvailabilitySelection() below.
let selectedAvailDays = new Set();
let selectedAvailWindowIndices = new Set();

function selectAvailDuration(minutes) {
  selectedDuration = minutes;
  document.querySelectorAll('#avail-duration-picker .window-btn').forEach(b => b.classList.toggle('selected', Number(b.dataset.duration) === minutes));
}

function toggleAvailDay(day) {
  if (selectedAvailDays.has(day)) selectedAvailDays.delete(day); else selectedAvailDays.add(day);
  document.querySelectorAll('#avail-day-picker .day-btn').forEach(b => b.classList.toggle('selected', selectedAvailDays.has(Number(b.dataset.day))));
}

function toggleAvailWindow(index) {
  if (selectedAvailWindowIndices.has(index)) selectedAvailWindowIndices.delete(index); else selectedAvailWindowIndices.add(index);
  document.querySelectorAll('#avail-window-picker .window-btn').forEach((b, i) => b.classList.toggle('selected', selectedAvailWindowIndices.has(i)));
}

function submitAvailabilitySelection() {
  const errorEl = document.getElementById('avail-error');
  errorEl.style.display = 'none';
  if (!selectedDuration) {
    errorEl.textContent = 'Pick a lesson length to continue.';
    errorEl.style.display = 'block';
    return;
  }
  if (selectedAvailDays.size === 0 || selectedAvailWindowIndices.size === 0) {
    errorEl.textContent = 'Pick at least one day and one time window to continue.';
    errorEl.style.display = 'block';
    return;
  }
  if (!document.getElementById('avail-address').value.trim() || !document.getElementById('avail-city').value.trim() || !document.getElementById('avail-state').value.trim()) {
    errorEl.textContent = 'Enter your address, city, and state to continue.';
    errorEl.style.display = 'block';
    return;
  }
  selectedWindows = [];
  for (const day of selectedAvailDays) {
    for (const windowIndex of selectedAvailWindowIndices) {
      const w = TIME_WINDOWS[windowIndex];
      selectedWindows.push({ day_of_week: day, start_time: w.start, end_time: w.end });
    }
  }
  const lessonsPerWeekRaw = document.getElementById('avail-lessons-per-week').value;
  selectedLessonsPerWeek = lessonsPerWeekRaw ? Number(lessonsPerWeekRaw) : null;

  loadPackages();
  goToScreen('package');
}

/* Mirrors lesson_requests.py's PACKAGE_DISCOUNT/_price_for exactly — the
   package list only ever shows the 30-min baseline price, so once a
   duration is picked the customer needs to see the real total before
   paying, not just find out on the match screen after submitting. */
function estimatedPackagePrice(pkg, durationMinutes) {
  const info = packageCatalog[pkg];
  const discount = info.price / (info.sessions * durationCatalog[30]);
  const perSession = Math.round(durationCatalog[durationMinutes] * discount);
  return perSession * info.sessions;
}

async function submitPayment(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('payment-error');
  errorEl.style.display = 'none';
  const submitBtn = document.getElementById('pay-submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Sending…';

  const payload = {
    specialty: selectedSpecialty,
    package: selectedPackage,
    address: document.getElementById('avail-address').value.trim(),
    city: document.getElementById('avail-city').value.trim(),
    state: document.getElementById('avail-state').value.trim(),
    duration_minutes: selectedDuration,
    availability_windows: selectedWindows.map(w => ({ day_of_week: w.day_of_week, start_time: w.start_time, end_time: w.end_time })),
    lessons_per_week: selectedLessonsPerWeek,
    notes: document.getElementById('pay-notes').value.trim() || null,
    preferred_instructor_id: preferredInstructorId,
    card_name: document.getElementById('pay-name').value.trim(),
    card_number: document.getElementById('pay-number').value.trim(),
    card_expiry: document.getElementById('pay-expiry').value.trim(),
    card_cvc: document.getElementById('pay-cvc').value.trim(),
  };

  try {
    const lessonRequest = await apiFetch('/api/customer/lesson-requests', { method: 'POST', body: JSON.stringify(payload) });
    lastRequestType = 'schedule';
    preferredInstructorId = null;
    preferredInstructorName = null;
    renderMatch(lessonRequest, true);
    goToScreen('match');
  } catch (err) {
    errorEl.textContent = err.message || 'Could not send request.';
    errorEl.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Send Request';
  }
}

/* =========================================================
   HISTORY + REVIEWS
   No in-app messaging, no separate review-form screen — reviews are a
   small inline expand right on each history card, since this app has no
   modal system (unlike the instructor app) and a whole new screen felt
   like overkill for "pick a star rating and an optional comment."
   ========================================================= */
let selectedStars = {};

async function openHistoryScreen() {
  goToScreen('history');
  await loadHistory();
}

async function loadHistory() {
  const listEl = document.getElementById('history-list');
  const emptyEl = document.getElementById('history-empty');
  try {
    const [bookings, lessonRequests, blocked, reviews] = await Promise.all([
      apiFetch('/api/customer/bookings'),
      apiFetch('/api/customer/lesson-requests'),
      apiFetch('/api/customer/blocks'),
      apiFetch('/api/customer/reviews'),
    ]);
    blockedInstructorIds = new Set(blocked.map(b => b.instructor_id));
    reviewsByKey = {};
    reviews.forEach(r => {
      const key = r.booking_id != null ? `booking-${r.booking_id}` : `lesson-request-${r.lesson_request_id}`;
      reviewsByKey[key] = r;
    });
    const items = [
      ...bookings.map(b => ({ ...b, _type: 'booking' })),
      ...lessonRequests.map(lr => ({ ...lr, _type: 'lesson-request' })),
    ].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

    if (items.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = items.map(historyCardHTML).join('');
      emptyEl.style.display = 'none';
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.textContent = "Couldn't load your history. Is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load history:', err);
  }
}

function historyCardHTML(item) {
  const specialtyLabel = item.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const statusLabel = { pending: 'Pending', matched: 'Matched', unmatched: 'Unmatched' }[item.status] || item.status;
  const dateStr = item.occurrence_date
    ? new Date(item.occurrence_date + 'T00:00:00').toLocaleDateString()
    : (item.created_at ? new Date(item.created_at).toLocaleDateString() : '');
  const instructorName = item.instructor ? item.instructor.name : null;
  const key = `${item._type}-${item.id}`;
  // Name travels through the onclick attribute URI-encoded (not just
  // escapeHtml'd) so an instructor's own display name — arbitrary,
  // user-supplied text — can never break out of the quoted JS argument.
  const encodedName = instructorName ? encodeURIComponent(instructorName) : '';
  const rebookCall = `rebookRequest(${item.instructor ? item.instructor.id : 'null'}, '${item.specialty}', '${encodedName}')`;
  // A row generated by a RecurringSeries (recurring_series_id set) already
  // *is* a standing booking — offering "make this standing" or "book
  // again" on it would just create a second, redundant series/request.
  const isRecurringOccurrence = item._type === 'lesson-request' && !!item.occurrence_date;
  const isBlocked = item.instructor && blockedInstructorIds.has(item.instructor.id);
  // Only a single-session request can become a standing weekly booking
  // (see recurring_series.py) — a multi-session package's remaining
  // sessions get scheduled one at a time instead, below.
  const canMakeRecurring = item._type === 'lesson-request' && !isRecurringOccurrence && item.sessions_total === 1;
  const isPackageRoot = item._type === 'lesson-request' && item.session_number === 1 && item.sessions_total > 1;
  const hasSessionsToSchedule = isPackageRoot && item.sessions_scheduled != null && item.sessions_scheduled < item.sessions_total;
  // A package root only self-serve-cancels before anything beyond the
  // root itself has been scheduled — matches the backend's 400 case
  // (see routers/lesson_requests.py's cancel_lesson_request).
  const packageHasScheduledSessions = isPackageRoot && item.sessions_scheduled != null && item.sessions_scheduled > 1;
  const canCancel = (item.status === 'pending' || item.status === 'matched') && !isRecurringOccurrence && !packageHasScheduledSessions;
  const showMatchedActions = item.status === 'matched' && item.instructor;
  const cancelBtn = canCancel ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="cancelHistoryItem('${item._type}', ${item.id})">Cancel Request</button>` : '';
  return `
    <div class="card wizard-card" style="margin:0 0 14px; padding:20px 22px; text-align:left;">
      <p class="card-sub" style="margin:0; text-align:left;">${escapeHtml(dateStr)} · ${escapeHtml(statusLabel)}${isRecurringOccurrence ? ' · Recurring' : ''}${isPackageRoot ? ` · ${item.sessions_scheduled} of ${item.sessions_total} scheduled` : ''}</p>
      <p class="match-name" style="font-size:17px; margin-top:4px;">${escapeHtml(specialtyLabel)}${instructorName ? ' with ' + escapeHtml(instructorName) : ''}</p>
      ${showMatchedActions ? `
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">
          <button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="toggleReviewForm('${key}')">${reviewsByKey[key] ? 'Edit Review' : 'Leave a Review'}</button>
          ${!isRecurringOccurrence ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="${rebookCall}">Book Again with ${escapeHtml(instructorName)}</button>` : ''}
          ${canMakeRecurring ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="makeRecurring(${item.id})">Make This Standing Weekly</button>` : ''}
          ${hasSessionsToSchedule ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="toggleScheduleNextForm('${key}', ${item.id})">Schedule Next Session (${item.sessions_scheduled} of ${item.sessions_total})</button>` : ''}
          <button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="toggleReportForm('${key}', ${item.instructor.id})">Report</button>
          <button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="toggleBlockInstructor(${item.instructor.id}, '${encodedName}')">${isBlocked ? 'Unblock' : 'Block'}</button>
          ${cancelBtn}
        </div>
        <div id="review-form-${key}" style="display:none; margin-top:14px;"></div>
        <div id="report-form-${key}" style="display:none; margin-top:14px;"></div>
        <div id="schedule-next-form-${key}" style="display:none; margin-top:14px;"></div>` : (cancelBtn ? `
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">${cancelBtn}</div>` : '')}
    </div>`;
}

/* =========================================================
   REPORT / BLOCK INSTRUCTOR
   Same inline-expand shape as the review form above — this app has no
   modal system, see the "no modal system" note near renderMatch.
   ========================================================= */
function toggleReportForm(key, instructorId) {
  const el = document.getElementById(`report-form-${key}`);
  if (el.style.display === 'block') {
    el.style.display = 'none';
    el.innerHTML = '';
    return;
  }
  el.style.display = 'block';
  el.innerHTML = `
    <select class="field-input" id="report-reason-${key}">
      <option value="no-show">No-show</option>
      <option value="harassment">Harassment or inappropriate behavior</option>
      <option value="safety">Safety concern</option>
      <option value="other">Other</option>
    </select>
    <textarea class="field-input" id="report-message-${key}" placeholder="Optional details" style="margin-top:8px; min-height:60px;"></textarea>
    <div id="report-error-${key}" class="form-error" style="display:none; margin-top:8px;"></div>
    <button class="btn btn-primary btn-block" style="margin-top:8px; padding:10px;" onclick="submitReport('${key}', ${instructorId})">Submit Report</button>`;
}

async function submitReport(key, instructorId) {
  const errorEl = document.getElementById(`report-error-${key}`);
  errorEl.style.display = 'none';
  const payload = {
    instructor_id: instructorId,
    reason: document.getElementById(`report-reason-${key}`).value,
    message: document.getElementById(`report-message-${key}`).value.trim() || null,
  };
  try {
    await apiFetch('/api/customer/reports', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById(`report-form-${key}`).style.display = 'none';
    document.getElementById(`report-form-${key}`).innerHTML = '';
    alert('Report submitted. An admin will review it.');
  } catch (err) {
    errorEl.textContent = err.message || 'Could not submit report.';
    errorEl.style.display = 'block';
  }
}

async function toggleBlockInstructor(instructorId, encodedName) {
  const name = decodeURIComponent(encodedName);
  const isBlocked = blockedInstructorIds.has(instructorId);
  const verb = isBlocked ? 'unblock' : 'block';
  if (!confirm(`${isBlocked ? 'Unblock' : 'Block'} ${name}? ${isBlocked ? '' : "You won't be matched with them again."}`)) return;
  try {
    if (isBlocked) {
      await apiFetch(`/api/customer/blocks/${instructorId}`, { method: 'DELETE' });
    } else {
      await apiFetch('/api/customer/blocks', { method: 'POST', body: JSON.stringify({ instructor_id: instructorId }) });
    }
    await loadHistory();
  } catch (err) {
    alert(err.message || `Could not ${verb} this instructor.`);
  }
}

async function cancelHistoryItem(type, id) {
  if (!confirm('Cancel this request?')) return;
  const path = type === 'lesson-request' ? `/api/customer/lesson-requests/${id}/cancel` : `/api/customer/bookings/${id}/cancel`;
  try {
    await apiFetch(path, { method: 'PUT' });
    await loadHistory();
  } catch (err) {
    alert(err.message || 'Could not cancel this request.');
  }
}

async function makeRecurring(lessonRequestId) {
  try {
    await apiFetch('/api/customer/recurring-series', { method: 'POST', body: JSON.stringify({ lesson_request_id: lessonRequestId }) });
    alert("You're set. This is now a standing weekly booking. See it under Recurring Bookings.");
    await loadHistory();
  } catch (err) {
    alert(err.message || 'Could not set up a standing booking.');
  }
}

/* =========================================================
   SCHEDULE NEXT SESSION
   Same inline-expand shape as the review/report forms above. A small
   self-contained day/window picker scoped to this one card's key (not
   the wizard's global selectedWindows) — default is "use my original
   availability", which just omits availability_windows from the POST.
   ========================================================= */
function toggleScheduleNextForm(key, rootId) {
  const el = document.getElementById(`schedule-next-form-${key}`);
  if (el.style.display === 'block') {
    el.style.display = 'none';
    el.innerHTML = '';
    return;
  }
  scheduleNextSelectedDays[key] = new Set();
  scheduleNextSelectedWindows[key] = new Set();
  el.style.display = 'block';
  el.innerHTML = `
    <label style="display:flex; align-items:center; gap:8px; font-size:14px; cursor:pointer;">
      <input type="checkbox" id="snext-use-original-${key}" checked onchange="toggleScheduleNextCustomWindows('${key}')"> Use my original availability
    </label>
    <div id="snext-custom-${key}" style="display:none; margin-top:10px;">
      <div class="day-picker" id="snext-day-picker-${key}">
        ${DAY_NAMES.map((name, i) => `<button type="button" class="day-btn" onclick="toggleScheduleNextDay('${key}', ${i})" data-day="${i}">${name.slice(0, 3)}</button>`).join('')}
      </div>
      <div class="window-grid" id="snext-window-picker-${key}" style="margin-top:10px;">
        ${TIME_WINDOWS.map((w, i) => `<button type="button" class="window-btn" onclick="toggleScheduleNextWindow('${key}', ${i})" data-window="${i}">${w.label}</button>`).join('')}
      </div>
    </div>
    <div id="snext-error-${key}" class="form-error" style="display:none; margin-top:8px;"></div>
    <button class="btn btn-primary btn-block" style="margin-top:10px; padding:10px;" onclick="submitScheduleNext('${key}', ${rootId})">Schedule It</button>`;
}

function toggleScheduleNextCustomWindows(key) {
  const useOriginal = document.getElementById(`snext-use-original-${key}`).checked;
  document.getElementById(`snext-custom-${key}`).style.display = useOriginal ? 'none' : 'block';
}

// Same toggle-is-the-selection shape as the main availability screen's
// pickers — no staging area, no add step, no chip list. See
// selectedAvailDays/selectedAvailWindowIndices above.
let scheduleNextSelectedDays = {};
let scheduleNextSelectedWindows = {};

function toggleScheduleNextDay(key, day) {
  const set = scheduleNextSelectedDays[key];
  if (set.has(day)) set.delete(day); else set.add(day);
  document.querySelectorAll(`#snext-day-picker-${key} .day-btn`).forEach(b => b.classList.toggle('selected', set.has(Number(b.dataset.day))));
}

function toggleScheduleNextWindow(key, index) {
  const set = scheduleNextSelectedWindows[key];
  if (set.has(index)) set.delete(index); else set.add(index);
  document.querySelectorAll(`#snext-window-picker-${key} .window-btn`).forEach((b, i) => b.classList.toggle('selected', set.has(i)));
}

async function submitScheduleNext(key, rootId) {
  const errorEl = document.getElementById(`snext-error-${key}`);
  errorEl.style.display = 'none';
  const useOriginal = document.getElementById(`snext-use-original-${key}`).checked;
  const payload = {};
  if (!useOriginal) {
    const days = scheduleNextSelectedDays[key];
    const windows = scheduleNextSelectedWindows[key];
    if (days.size === 0 || windows.size === 0) {
      errorEl.textContent = 'Pick at least one day and one time window, or use your original availability.';
      errorEl.style.display = 'block';
      return;
    }
    const windowsPayload = [];
    for (const day of days) {
      for (const windowIndex of windows) {
        const w = TIME_WINDOWS[windowIndex];
        windowsPayload.push({ day_of_week: day, start_time: w.start, end_time: w.end });
      }
    }
    payload.availability_windows = windowsPayload;
  }
  try {
    await apiFetch(`/api/customer/lesson-requests/${rootId}/schedule-next`, { method: 'POST', body: JSON.stringify(payload) });
    await loadHistory();
  } catch (err) {
    errorEl.textContent = err.message || 'Could not schedule the next session.';
    errorEl.style.display = 'block';
  }
}

function toggleReviewForm(key) {
  const el = document.getElementById(`review-form-${key}`);
  if (el.style.display === 'block') {
    el.style.display = 'none';
    el.innerHTML = '';
    return;
  }
  const existing = reviewsByKey[key];
  el.style.display = 'block';
  el.innerHTML = `
    <div class="star-picker" id="stars-${key}">
      ${[1, 2, 3, 4, 5].map(n => `<span class="star" data-star="${n}" onclick="selectStar('${key}', ${n})">★</span>`).join('')}
    </div>
    <textarea class="field-input" id="comment-${key}" placeholder="Optional comment" style="margin-top:8px; min-height:60px;">${existing ? escapeHtml(existing.comment || '') : ''}</textarea>
    <div id="review-error-${key}" class="form-error" style="display:none; margin-top:8px;"></div>
    <div style="display:flex; gap:8px; margin-top:8px;">
      <button class="btn btn-primary btn-block" style="padding:10px;" onclick="submitReview('${key}')">${existing ? 'Update Review' : 'Submit Review'}</button>
      ${existing ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="deleteReview('${key}')">Delete Review</button>` : ''}
    </div>`;
  if (existing) selectStar(key, existing.rating);
}

function selectStar(key, n) {
  selectedStars[key] = n;
  document.querySelectorAll(`#stars-${key} .star`).forEach(s => {
    s.classList.toggle('selected', Number(s.dataset.star) <= n);
  });
}

async function submitReview(key) {
  const dashIndex = key.lastIndexOf('-');
  const type = key.slice(0, dashIndex);
  const id = Number(key.slice(dashIndex + 1));
  const existing = reviewsByKey[key];
  const rating = selectedStars[key];
  const errorEl = document.getElementById(`review-error-${key}`);
  errorEl.style.display = 'none';
  if (!rating) {
    errorEl.textContent = 'Pick a star rating.';
    errorEl.style.display = 'block';
    return;
  }
  const comment = document.getElementById(`comment-${key}`).value.trim() || null;
  try {
    if (existing) {
      await apiFetch(`/api/customer/reviews/${existing.id}`, { method: 'PUT', body: JSON.stringify({ rating, comment }) });
    } else {
      const payload = { rating, comment };
      if (type === 'lesson-request') payload.lesson_request_id = id; else payload.booking_id = id;
      await apiFetch('/api/customer/reviews', { method: 'POST', body: JSON.stringify(payload) });
    }
    await loadHistory();
  } catch (err) {
    errorEl.textContent = err.message || 'Could not submit review.';
    errorEl.style.display = 'block';
  }
}

async function deleteReview(key) {
  const existing = reviewsByKey[key];
  if (!existing) return;
  if (!confirm('Delete this review? This cannot be undone.')) return;
  try {
    await apiFetch(`/api/customer/reviews/${existing.id}`, { method: 'DELETE' });
    await loadHistory();
  } catch (err) {
    alert(err.message || 'Could not delete this review.');
  }
}

/* =========================================================
   RECURRING BOOKINGS
   Manage screen for standing weekly bookings created via "Make This
   Standing Weekly" above. Occurrences themselves just show up as normal
   matched entries in History (tagged "Recurring") — this screen is only
   for managing the series itself (pause/resume/cancel).
   ========================================================= */
async function openRecurringScreen() {
  goToScreen('recurring');
  await loadRecurringSeries();
}

async function loadRecurringSeries() {
  const listEl = document.getElementById('recurring-list');
  const emptyEl = document.getElementById('recurring-empty');
  try {
    const series = await apiFetch('/api/customer/recurring-series');
    if (series.length === 0) {
      listEl.innerHTML = '';
      emptyEl.style.display = 'block';
    } else {
      listEl.innerHTML = series.map(recurringCardHTML).join('');
      emptyEl.style.display = 'none';
    }
  } catch (err) {
    listEl.innerHTML = '';
    emptyEl.textContent = "Couldn't load your recurring bookings. Is the backend running?";
    emptyEl.style.display = 'block';
    console.error('Failed to load recurring series:', err);
  }
}

function recurringCardHTML(series) {
  const specialtyLabel = series.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const instructorName = series.instructor ? series.instructor.name : 'an instructor';
  const statusLabel = { active: 'Active', paused: 'Paused', cancelled: 'Cancelled' }[series.status] || series.status;
  const actions = series.status === 'active'
    ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="pauseSeries(${series.id})">Pause</button>
       <button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="cancelSeries(${series.id})">Cancel</button>`
    : series.status === 'paused'
    ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="resumeSeries(${series.id})">Resume</button>
       <button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="cancelSeries(${series.id})">Cancel</button>`
    : '';
  return `
    <div class="card wizard-card" style="margin:0 0 14px; padding:20px 22px; text-align:left;">
      <p class="card-sub" style="margin:0; text-align:left;">${escapeHtml(statusLabel)}</p>
      <p class="match-name" style="font-size:17px; margin-top:4px;">${escapeHtml(specialtyLabel)} with ${escapeHtml(instructorName)}</p>
      <p class="card-sub" style="text-align:left; margin-top:4px;">Every ${DAY_NAMES[series.day_of_week]}, ${series.start_time}–${series.end_time} · $${series.price_per_lesson}/lesson</p>
      ${actions ? `<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">${actions}</div>` : ''}
    </div>`;
}

async function pauseSeries(id) {
  try {
    await apiFetch(`/api/customer/recurring-series/${id}/pause`, { method: 'PUT' });
    await loadRecurringSeries();
  } catch (err) {
    alert(err.message || 'Could not pause this booking.');
  }
}

async function resumeSeries(id) {
  try {
    await apiFetch(`/api/customer/recurring-series/${id}/resume`, { method: 'PUT' });
    await loadRecurringSeries();
  } catch (err) {
    alert(err.message || 'Could not resume this booking.');
  }
}

async function cancelSeries(id) {
  if (!confirm('Cancel this standing weekly booking? Already-scheduled upcoming lessons stay on your calendar, only future ones stop being created.')) return;
  try {
    await apiFetch(`/api/customer/recurring-series/${id}`, { method: 'DELETE' });
    await loadRecurringSeries();
  } catch (err) {
    alert(err.message || 'Could not cancel this booking.');
  }
}

/* =========================================================
   MATCH DISPLAY
   Handles both result shapes: a package Booking and a scheduled
   LessonRequest — distinguished by the presence of `requested_day`,
   a field only LessonRequestOut has. Also handles three statuses now
   instead of two: "pending" (broadcast to instructors, awaiting
   confirmation — nothing charged yet), "matched" (an instructor
   confirmed and the card was charged), and "unmatched" (true dead end,
   no active instructor could ever fulfill this).
   ========================================================= */
function renderMatch(result, justBooked) {
  const isLessonRequest = 'requested_day' in result;
  const specialtyLabel = result.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  lastRequestId = result.id;

  const ctaBtn = document.getElementById('match-cta-btn');
  ctaBtn.textContent = isLessonRequest ? 'Schedule Another Lesson' : 'Book Another Package';
  ctaBtn.onclick = () => goToScreen('specialty');

  const pendingEl = document.getElementById('match-pending');
  const unmatchedEl = document.getElementById('match-unmatched');
  const contactEl = document.getElementById('match-contact');
  const refreshBtn = document.getElementById('match-refresh-btn');
  const cancelBtn = document.getElementById('match-cancel-btn');
  pendingEl.style.display = 'none';
  unmatchedEl.style.display = 'none';
  contactEl.style.display = 'none';
  refreshBtn.style.display = result.status === 'pending' ? 'block' : 'none';
  // Only offered here while still pending — a matched/unmatched request
  // is already reachable (and, for matched, cancellable) from History.
  cancelBtn.style.display = result.status === 'pending' ? 'block' : 'none';

  if (result.status === 'pending') {
    document.getElementById('match-eyebrow').textContent = 'Request sent';
    // requested_day is null until a specific instructor confirms one of
    // the submitted windows (see models.LessonRequest's docstring) — show
    // a window-count summary instead while still pending.
    const windowCount = result.availability_windows ? result.availability_windows.length : 0;
    const summary = isLessonRequest
      ? result.requested_day != null
        ? `${DAY_NAMES[result.requested_day]}, ${result.requested_start_time}–${result.requested_end_time} · ${result.duration_minutes} min · ${specialtyLabel} · $${result.amount_paid} due once confirmed`
        : `${result.sessions_total} session${result.sessions_total > 1 ? 's' : ''} · ${windowCount} window${windowCount === 1 ? '' : 's'} submitted · ${result.duration_minutes} min · ${specialtyLabel} · $${result.amount_paid} due once confirmed`
      : `${result.sessions_total} session${result.sessions_total > 1 ? 's' : ''} · ${specialtyLabel} · $${result.amount_paid} due once confirmed`;
    document.getElementById('match-summary').textContent = summary;
    document.getElementById('match-avatar').textContent = '···';
    document.getElementById('match-name').textContent = 'Waiting for an instructor';
    document.getElementById('match-specialty-badge').textContent = specialtyLabel;
    document.getElementById('match-bio').textContent = '';
    document.getElementById('match-certs').textContent = '';
    pendingEl.textContent = "We've sent your request to nearby instructors who offer this. You'll be matched (and your card charged) as soon as one confirms. Check back any time.";
    pendingEl.style.display = 'block';
    return;
  }

  document.getElementById('match-eyebrow').textContent = justBooked ? "You're matched!" : 'Your match';

  // A self- or admin-cancelled request only ever reaches this branch
  // with no instructor attached (the Cancel button only shows while
  // still "pending" — see cancelCurrentRequest) — cancelled_by_admin is
  // included here too since /me has no status filter and could surface
  // one just as easily. Without this, it'd fall through to the generic
  // "no instructor could fulfill" copy below, which is simply wrong for
  // a request the customer cancelled themselves.
  const isCancelled = result.status === 'cancelled_by_customer' || result.status === 'cancelled_by_admin';
  unmatchedEl.textContent = isCancelled
    ? 'This request was cancelled.'
    : isLessonRequest
      ? "No instructor could fulfill any of those windows. Try different days, times, or a shorter lesson length."
      : "No active instructor currently offers this specialty. Please check back later.";

  if (!result.instructor) {
    // Truly unmatched: requested_day/matched_start_time are never set on
    // a row that never got confirmed, so there's no real day/time to
    // summarize here — unmatchedEl above already carries the message.
    document.getElementById('match-summary').textContent = `${specialtyLabel} · $${result.amount_paid} due once confirmed`;
    document.getElementById('match-avatar').textContent = '···';
    document.getElementById('match-name').textContent = isCancelled ? 'Cancelled' : 'Not matched';
    document.getElementById('match-specialty-badge').textContent = specialtyLabel;
    document.getElementById('match-bio').textContent = '';
    document.getElementById('match-certs').textContent = '';
    unmatchedEl.style.display = 'block';
    return;
  }

  const summary = isLessonRequest
    ? `${DAY_NAMES[result.requested_day]}, ${result.matched_start_time || result.requested_start_time}–${result.matched_end_time || result.requested_end_time} · ${specialtyLabel} · $${result.amount_paid} paid`
    : `$${result.amount_paid} paid · ${result.sessions_total} session${result.sessions_total > 1 ? 's' : ''} · ${specialtyLabel}`;
  document.getElementById('match-summary').textContent = summary;

  const instructor = result.instructor;
  const initials = instructor.name.split(' ').filter(Boolean).map(w => w[0].toUpperCase()).slice(0, 2).join('');
  document.getElementById('match-avatar').textContent = initials;
  document.getElementById('match-name').textContent = instructor.name;
  document.getElementById('match-specialty-badge').textContent = specialtyLabel;
  document.getElementById('match-bio').textContent = instructor.bio;
  document.getElementById('match-certs').textContent = isLessonRequest && result.distance_km != null
    ? `${instructor.certifications} · ~${result.distance_km} km away`
    : instructor.certifications;

  contactEl.innerHTML = `<b>Contact ${escapeHtml(instructor.name)}:</b><br>${escapeHtml(instructor.email)}<br>${escapeHtml(instructor.phone)}`;
  contactEl.style.display = 'block';
}

async function checkLatestStatus() {
  if (!lastRequestType) return;
  try {
    const path = lastRequestType === 'schedule' ? '/api/customer/lesson-requests/me' : '/api/customer/bookings/me';
    const result = await apiFetch(path);
    renderMatch(result, false);
  } catch (err) {
    console.error('Failed to refresh status:', err);
  }
}

async function cancelCurrentRequest() {
  if (!lastRequestId) return;
  if (!confirm('Cancel this request?')) return;
  const path = lastRequestType === 'schedule'
    ? `/api/customer/lesson-requests/${lastRequestId}/cancel`
    : `/api/customer/bookings/${lastRequestId}/cancel`;
  try {
    const result = await apiFetch(path, { method: 'PUT' });
    renderMatch(result, false);
  } catch (err) {
    alert(err.message || 'Could not cancel this request.');
  }
}

/* =========================================================
   BOOT
   ========================================================= */
async function routeLoggedInCustomer() {
  // Try both flows since a customer might have used either one. Neither
  // response exposes a timestamp to compare, so on the rare chance both
  // exist we just prefer the lesson request — a reasonable, documented
  // simplification for a learning project rather than true "most recent".
  try {
    const lessonRequest = await apiFetch('/api/customer/lesson-requests/me');
    lastRequestType = 'schedule';
    renderMatch(lessonRequest, false);
    goToScreen('match');
    return;
  } catch (err) {
    // No lesson request yet (404) — fall through and check for a booking.
  }
  try {
    const booking = await apiFetch('/api/customer/bookings/me');
    lastRequestType = 'package';
    renderMatch(booking, false);
    goToScreen('match');
  } catch (err) {
    // Neither exists yet — start the wizard.
    goToScreen('specialty');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  updateNav();
  const resetToken = new URLSearchParams(window.location.search).get('reset_token');
  if (resetToken) {
    history.replaceState(null, '', window.location.pathname);
    pendingResetToken = resetToken;
    goToScreen('reset-password');
    return;
  }
  if (getToken()) {
    routeLoggedInCustomer();
  }
  initGoogleSignIn();
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/customer/sw.js');
}
