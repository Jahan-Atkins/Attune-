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
const TIME_WINDOWS = [
  { label: '9–11am', start: '09:00', end: '11:00' },
  { label: '11am–1pm', start: '11:00', end: '13:00' },
  { label: '1–3pm', start: '13:00', end: '15:00' },
  { label: '3–5pm', start: '15:00', end: '17:00' },
];
let selectedDay = null;
let selectedWindow = null;
let selectedDuration = null;
let citiesCache = [];
let durationCatalog = {};
let lastRequestType = null; // 'package' | 'schedule' — which /me endpoint checkLatestStatus() re-polls
let preferredInstructorId = null; // set by "Book Again with [Name]", sent as-is in the final submit payload
let preferredInstructorName = null; // display-only echo of the above, never sent to the backend

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
  document.getElementById('auth-name').required = isSignup;
  document.getElementById('auth-phone').required = isSignup;
  document.getElementById('auth-title').textContent = isSignup ? 'Create Your Account' : 'Log In';
  document.getElementById('auth-sub').textContent = isSignup ? 'Takes about a minute.' : 'Welcome back.';
  document.getElementById('auth-submit-btn').textContent = isSignup ? 'Create Account' : 'Log In';
  document.getElementById('auth-toggle-btn').textContent = isSignup ? 'Already have an account? Log in' : 'New here? Create an account';
  document.getElementById('auth-error').style.display = 'none';
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
   WIZARD: specialty -> package -> payment -> match
   ========================================================= */
async function goToSpecialtyStep() {
  goToScreen('specialty');
}

function selectSpecialty(specialty) {
  preferredInstructorId = null; // a fresh specialty pick always means a regular (broadcast) request
  preferredInstructorName = null;
  selectedSpecialty = specialty;
  goToScreen('booking-type');
}

/* Rebooking — "Book Again with [Name]" on a matched History card. Skips
   straight to the package/schedule step the normal wizard would only
   reach after picking a specialty and a booking type, since both are
   already implied by the past match being rebooked. */
function rebookPackage(instructorId, specialty, encodedInstructorName) {
  preferredInstructorId = instructorId;
  preferredInstructorName = decodeURIComponent(encodedInstructorName || '');
  selectedSpecialty = specialty;
  loadPackages();
  goToScreen('package');
}

async function rebookSchedule(instructorId, specialty, durationMinutes, encodedInstructorName) {
  preferredInstructorId = instructorId;
  preferredInstructorName = decodeURIComponent(encodedInstructorName || '');
  selectedSpecialty = specialty;
  await initScheduleStep();
  selectScheduleDuration(durationMinutes);
  goToScreen('schedule');
}

function chooseBookingType(type) {
  if (type === 'package') {
    loadPackages();
    goToScreen('package');
  } else {
    initScheduleStep();
    goToScreen('schedule');
  }
}

async function loadPackages() {
  const listEl = document.getElementById('package-list');
  listEl.innerHTML = '<p class="card-sub">Loading packages…</p>';
  try {
    packageCatalog = await apiFetch('/api/customer/bookings/packages');
    const labels = { single: 'Single Session', pack4: '4-Session Package', pack8: '8-Session Package' };
    listEl.innerHTML = Object.entries(packageCatalog).map(([key, info]) => {
      const perSession = (info.price / info.sessions).toFixed(0);
      return `
        <button class="package-card" onclick="selectPackage('${key}')">
          <div>
            <p class="package-name">${labels[key] || key}</p>
            <p class="package-meta">${info.sessions} session${info.sessions > 1 ? 's' : ''} · $${perSession}/session</p>
          </div>
          <p class="package-price">$${info.price}</p>
        </button>`;
    }).join('');
  } catch (err) {
    listEl.innerHTML = `<p class="form-error">Couldn't load packages — is the backend running?</p>`;
    console.error(err);
  }
}

async function selectPackage(pkg) {
  selectedPackage = pkg;
  const info = packageCatalog[pkg];
  const specialtyLabel = selectedSpecialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const rebookNote = preferredInstructorId ? ` · Booking again with ${preferredInstructorName}` : '';
  document.getElementById('payment-summary').textContent =
    `${specialtyLabel} · ${info.sessions} session${info.sessions > 1 ? 's' : ''} · $${info.price}${rebookNote}`;

  const cities = await loadCities();
  document.getElementById('pay-city').innerHTML = cities.map(c => `<option value="${c}">${c}</option>`).join('');

  goToScreen('payment');
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
    city: document.getElementById('pay-city').value,
    notes: document.getElementById('pay-notes').value.trim() || null,
    preferred_instructor_id: preferredInstructorId,
    card_name: document.getElementById('pay-name').value.trim(),
    card_number: document.getElementById('pay-number').value.trim(),
    card_expiry: document.getElementById('pay-expiry').value.trim(),
    card_cvc: document.getElementById('pay-cvc').value.trim(),
  };

  try {
    const booking = await apiFetch('/api/customer/bookings', { method: 'POST', body: JSON.stringify(payload) });
    lastRequestType = 'package';
    preferredInstructorId = null;
    preferredInstructorName = null;
    renderMatch(booking, true);
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
   WIZARD: schedule a specific lesson (day/time/city -> payment -> match)
   ========================================================= */
async function loadCities() {
  if (citiesCache.length) return citiesCache;
  try {
    citiesCache = await apiFetch('/api/cities');
  } catch (err) {
    console.error('Failed to load cities:', err);
  }
  return citiesCache;
}

async function loadDurations() {
  if (Object.keys(durationCatalog).length) return durationCatalog;
  try {
    durationCatalog = await apiFetch('/api/customer/lesson-requests/durations');
  } catch (err) {
    console.error('Failed to load durations:', err);
  }
  return durationCatalog;
}

async function initScheduleStep() {
  selectedDay = null;
  selectedWindow = null;
  selectedDuration = null;

  const durations = await loadDurations();
  const durationEl = document.getElementById('schedule-duration-picker');
  durationEl.innerHTML = Object.entries(durations).map(([minutes, price]) =>
    `<button type="button" class="window-btn" data-duration="${minutes}" onclick="selectScheduleDuration(${minutes})">${minutes} min · $${price}</button>`
  ).join('');

  const dayEl = document.getElementById('schedule-day-picker');
  dayEl.innerHTML = DAY_NAMES.map((name, i) =>
    `<button type="button" class="day-btn" data-day="${i}" onclick="selectScheduleDay(${i})">${name.slice(0, 3)}</button>`
  ).join('');

  const windowEl = document.getElementById('schedule-window-picker');
  windowEl.innerHTML = TIME_WINDOWS.map((w, i) =>
    `<button type="button" class="window-btn" data-window="${i}" onclick="selectScheduleWindow(${i})">${w.label}</button>`
  ).join('');

  const cities = await loadCities();
  const cityEl = document.getElementById('schedule-city');
  cityEl.innerHTML = cities.map(c => `<option value="${c}">${c}</option>`).join('');
}

function selectScheduleDuration(minutes) {
  selectedDuration = minutes;
  document.querySelectorAll('#schedule-duration-picker .window-btn').forEach(b => b.classList.toggle('selected', Number(b.dataset.duration) === minutes));
}

function selectScheduleDay(day) {
  selectedDay = day;
  document.querySelectorAll('#schedule-day-picker .day-btn').forEach(b => b.classList.toggle('selected', Number(b.dataset.day) === day));
}

function selectScheduleWindow(index) {
  selectedWindow = TIME_WINDOWS[index];
  document.querySelectorAll('#schedule-window-picker .window-btn').forEach((b, i) => b.classList.toggle('selected', i === index));
}

function submitScheduleSelection() {
  const errorEl = document.getElementById('schedule-error');
  errorEl.style.display = 'none';
  if (!selectedDuration) {
    errorEl.textContent = 'Pick a lesson length to continue.';
    errorEl.style.display = 'block';
    return;
  }
  if (selectedDay === null || !selectedWindow) {
    errorEl.textContent = 'Pick a day and a time window to continue.';
    errorEl.style.display = 'block';
    return;
  }
  const specialtyLabel = selectedSpecialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const city = document.getElementById('schedule-city').value;
  const price = durationCatalog[selectedDuration];
  const rebookNote = preferredInstructorId ? ` · Booking again with ${preferredInstructorName}` : '';
  document.getElementById('schedule-payment-summary').textContent =
    `${specialtyLabel} · ${selectedDuration} min · ${DAY_NAMES[selectedDay]}, ${selectedWindow.label} · ${city} · $${price}${rebookNote}`;
  goToScreen('schedule-payment');
}

async function submitSchedulePayment(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('schedule-payment-error');
  errorEl.style.display = 'none';
  const submitBtn = document.getElementById('spay-submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Sending…';

  const payload = {
    specialty: selectedSpecialty,
    city: document.getElementById('schedule-city').value,
    duration_minutes: selectedDuration,
    requested_day: selectedDay,
    requested_start_time: selectedWindow.start,
    requested_end_time: selectedWindow.end,
    notes: document.getElementById('spay-notes').value.trim() || null,
    preferred_instructor_id: preferredInstructorId,
    card_name: document.getElementById('spay-name').value.trim(),
    card_number: document.getElementById('spay-number').value.trim(),
    card_expiry: document.getElementById('spay-expiry').value.trim(),
    card_cvc: document.getElementById('spay-cvc').value.trim(),
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
    const [bookings, lessonRequests] = await Promise.all([
      apiFetch('/api/customer/bookings'),
      apiFetch('/api/customer/lesson-requests'),
    ]);
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
    emptyEl.textContent = "Couldn't load your history — is the backend running?";
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
  const rebookCall = item._type === 'lesson-request'
    ? `rebookSchedule(${item.instructor ? item.instructor.id : 'null'}, '${item.specialty}', ${item.duration_minutes}, '${encodedName}')`
    : `rebookPackage(${item.instructor ? item.instructor.id : 'null'}, '${item.specialty}', '${encodedName}')`;
  // A row generated by a RecurringSeries (recurring_series_id set) already
  // *is* a standing booking — offering "make this standing" or "book
  // again" on it would just create a second, redundant series/request.
  const isRecurringOccurrence = item._type === 'lesson-request' && !!item.occurrence_date;
  return `
    <div class="card wizard-card" style="margin:0 0 14px; padding:20px 22px; text-align:left;">
      <p class="card-sub" style="margin:0; text-align:left;">${escapeHtml(dateStr)} · ${escapeHtml(statusLabel)}${isRecurringOccurrence ? ' · Recurring' : ''}</p>
      <p class="match-name" style="font-size:17px; margin-top:4px;">${escapeHtml(specialtyLabel)}${instructorName ? ' with ' + escapeHtml(instructorName) : ''}</p>
      ${item.status === 'matched' && item.instructor ? `
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px;">
          <button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="toggleReviewForm('${key}')">Leave a Review</button>
          ${!isRecurringOccurrence ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="${rebookCall}">Book Again with ${escapeHtml(instructorName)}</button>` : ''}
          ${item._type === 'lesson-request' && !isRecurringOccurrence ? `<button class="btn btn-outline" style="padding:10px 16px; font-size:13px;" onclick="makeRecurring(${item.id})">Make This Standing Weekly</button>` : ''}
        </div>
        <div id="review-form-${key}" style="display:none; margin-top:14px;"></div>` : ''}
    </div>`;
}

async function makeRecurring(lessonRequestId) {
  try {
    await apiFetch('/api/customer/recurring-series', { method: 'POST', body: JSON.stringify({ lesson_request_id: lessonRequestId }) });
    alert("You're set — this is now a standing weekly booking. See it under Recurring Bookings.");
    await loadHistory();
  } catch (err) {
    alert(err.message || 'Could not set up a standing booking.');
  }
}

function toggleReviewForm(key) {
  const el = document.getElementById(`review-form-${key}`);
  if (el.style.display === 'block') {
    el.style.display = 'none';
    el.innerHTML = '';
    return;
  }
  el.style.display = 'block';
  el.innerHTML = `
    <div class="star-picker" id="stars-${key}">
      ${[1, 2, 3, 4, 5].map(n => `<span class="star" data-star="${n}" onclick="selectStar('${key}', ${n})">★</span>`).join('')}
    </div>
    <textarea class="field-input" id="comment-${key}" placeholder="Optional comment" style="margin-top:8px; min-height:60px;"></textarea>
    <div id="review-error-${key}" class="form-error" style="display:none; margin-top:8px;"></div>
    <button class="btn btn-primary btn-block" style="margin-top:8px; padding:10px;" onclick="submitReview('${key}')">Submit Review</button>`;
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
  const rating = selectedStars[key];
  const errorEl = document.getElementById(`review-error-${key}`);
  errorEl.style.display = 'none';
  if (!rating) {
    errorEl.textContent = 'Pick a star rating.';
    errorEl.style.display = 'block';
    return;
  }
  const payload = { rating, comment: document.getElementById(`comment-${key}`).value.trim() || null };
  if (type === 'lesson-request') payload.lesson_request_id = id; else payload.booking_id = id;
  try {
    await apiFetch('/api/customer/reviews', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById(`review-form-${key}`).innerHTML = '<p class="card-sub" style="text-align:left; margin:0;">Thanks for your review!</p>';
  } catch (err) {
    errorEl.textContent = err.message || 'Could not submit review.';
    errorEl.style.display = 'block';
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
    emptyEl.textContent = "Couldn't load your recurring bookings — is the backend running?";
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
  if (!confirm('Cancel this standing weekly booking? Already-scheduled upcoming lessons stay on your calendar — only future ones stop being created.')) return;
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

  const ctaBtn = document.getElementById('match-cta-btn');
  ctaBtn.textContent = isLessonRequest ? 'Schedule Another Lesson' : 'Book Another Package';
  ctaBtn.onclick = () => goToScreen('specialty');

  const pendingEl = document.getElementById('match-pending');
  const unmatchedEl = document.getElementById('match-unmatched');
  const contactEl = document.getElementById('match-contact');
  const refreshBtn = document.getElementById('match-refresh-btn');
  pendingEl.style.display = 'none';
  unmatchedEl.style.display = 'none';
  contactEl.style.display = 'none';
  refreshBtn.style.display = result.status === 'pending' ? 'block' : 'none';

  if (result.status === 'pending') {
    document.getElementById('match-eyebrow').textContent = 'Request sent';
    const summary = isLessonRequest
      ? `${DAY_NAMES[result.requested_day]}, ${result.requested_start_time}–${result.requested_end_time} · ${result.duration_minutes} min · ${specialtyLabel} · $${result.amount_paid} due once confirmed`
      : `${result.sessions_total} session${result.sessions_total > 1 ? 's' : ''} · ${specialtyLabel} · $${result.amount_paid} due once confirmed`;
    document.getElementById('match-summary').textContent = summary;
    document.getElementById('match-avatar').textContent = '···';
    document.getElementById('match-name').textContent = 'Waiting for an instructor';
    document.getElementById('match-specialty-badge').textContent = specialtyLabel;
    document.getElementById('match-bio').textContent = '';
    document.getElementById('match-certs').textContent = '';
    pendingEl.textContent = "We've sent your request to nearby instructors who offer this — you'll be matched (and your card charged) as soon as one confirms. Check back any time.";
    pendingEl.style.display = 'block';
    return;
  }

  document.getElementById('match-eyebrow').textContent = justBooked ? "You're matched!" : 'Your match';
  const summary = isLessonRequest
    ? `${DAY_NAMES[result.requested_day]}, ${result.matched_start_time || result.requested_start_time}–${result.matched_end_time || result.requested_end_time} · ${specialtyLabel} · $${result.amount_paid} paid`
    : `$${result.amount_paid} paid · ${result.sessions_total} session${result.sessions_total > 1 ? 's' : ''} · ${specialtyLabel}`;
  document.getElementById('match-summary').textContent = summary;

  unmatchedEl.textContent = isLessonRequest
    ? "No instructor could fulfill that window — try a different day, time, or lesson length, or choose a package instead."
    : "No active instructor currently offers this specialty — please check back later.";

  if (!result.instructor) {
    document.getElementById('match-avatar').textContent = '···';
    document.getElementById('match-name').textContent = 'Not matched';
    document.getElementById('match-specialty-badge').textContent = specialtyLabel;
    document.getElementById('match-bio').textContent = '';
    document.getElementById('match-certs').textContent = '';
    unmatchedEl.style.display = 'block';
    return;
  }
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
  if (getToken()) {
    routeLoggedInCustomer();
  }
});
