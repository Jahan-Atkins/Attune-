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
let citiesCache = [];

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
      const res = await fetch('/api/customer/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
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
  selectedSpecialty = specialty;
  goToScreen('booking-type');
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

function selectPackage(pkg) {
  selectedPackage = pkg;
  const info = packageCatalog[pkg];
  const specialtyLabel = selectedSpecialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  document.getElementById('payment-summary').textContent =
    `${specialtyLabel} · ${info.sessions} session${info.sessions > 1 ? 's' : ''} · $${info.price}`;
  goToScreen('payment');
}

async function submitPayment(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('payment-error');
  errorEl.style.display = 'none';
  const submitBtn = document.getElementById('pay-submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Processing…';

  const payload = {
    specialty: selectedSpecialty,
    package: selectedPackage,
    card_name: document.getElementById('pay-name').value.trim(),
    card_number: document.getElementById('pay-number').value.trim(),
    card_expiry: document.getElementById('pay-expiry').value.trim(),
    card_cvc: document.getElementById('pay-cvc').value.trim(),
  };

  try {
    const booking = await apiFetch('/api/customer/bookings', { method: 'POST', body: JSON.stringify(payload) });
    renderMatch(booking, true);
    goToScreen('match');
  } catch (err) {
    errorEl.textContent = err.message || 'Payment failed.';
    errorEl.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Confirm & Get Matched';
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

async function initScheduleStep() {
  selectedDay = null;
  selectedWindow = null;

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
  if (selectedDay === null || !selectedWindow) {
    errorEl.textContent = 'Pick a day and a time window to continue.';
    errorEl.style.display = 'block';
    return;
  }
  const specialtyLabel = selectedSpecialty === 'yoga' ? 'Yoga' : 'Sound Bath';
  const city = document.getElementById('schedule-city').value;
  document.getElementById('schedule-payment-summary').textContent =
    `${specialtyLabel} · ${DAY_NAMES[selectedDay]}, ${selectedWindow.label} · ${city} · $65`;
  goToScreen('schedule-payment');
}

async function submitSchedulePayment(evt) {
  evt.preventDefault();
  const errorEl = document.getElementById('schedule-payment-error');
  errorEl.style.display = 'none';
  const submitBtn = document.getElementById('spay-submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Processing…';

  const payload = {
    specialty: selectedSpecialty,
    city: document.getElementById('schedule-city').value,
    requested_day: selectedDay,
    requested_start_time: selectedWindow.start,
    requested_end_time: selectedWindow.end,
    card_name: document.getElementById('spay-name').value.trim(),
    card_number: document.getElementById('spay-number').value.trim(),
    card_expiry: document.getElementById('spay-expiry').value.trim(),
    card_cvc: document.getElementById('spay-cvc').value.trim(),
  };

  try {
    const lessonRequest = await apiFetch('/api/customer/lesson-requests', { method: 'POST', body: JSON.stringify(payload) });
    renderMatch(lessonRequest, true);
    goToScreen('match');
  } catch (err) {
    errorEl.textContent = err.message || 'Payment failed.';
    errorEl.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Confirm & Get Matched';
  }
}

/* =========================================================
   MATCH DISPLAY
   Handles both result shapes: a package Booking and a scheduled
   LessonRequest — distinguished by the presence of `requested_day`,
   a field only LessonRequestOut has.
   ========================================================= */
function renderMatch(result, justBooked) {
  const isLessonRequest = 'requested_day' in result;
  document.getElementById('match-eyebrow').textContent = justBooked ? "You're matched!" : 'Your match';
  const specialtyLabel = result.specialty === 'yoga' ? 'Yoga' : 'Sound Bath';

  const ctaBtn = document.getElementById('match-cta-btn');
  ctaBtn.textContent = isLessonRequest ? 'Schedule Another Lesson' : 'Book Another Package';
  ctaBtn.onclick = () => goToScreen('specialty');

  const summary = isLessonRequest
    ? `${DAY_NAMES[result.requested_day]}, ${result.matched_start_time || result.requested_start_time}–${result.matched_end_time || result.requested_end_time} · ${specialtyLabel} · $${result.amount_paid} paid`
    : `$${result.amount_paid} paid · ${result.sessions_total} session${result.sessions_total > 1 ? 's' : ''} · ${specialtyLabel}`;
  document.getElementById('match-summary').textContent = summary;

  const unmatchedEl = document.getElementById('match-unmatched');
  unmatchedEl.textContent = isLessonRequest
    ? "No instructor was free in that window — try a different day or time, or choose a package instead and we'll match you whenever one's available."
    : "No active instructor currently offers this specialty — we'll match you as soon as one's available.";

  if (!result.instructor) {
    document.getElementById('match-avatar').textContent = '···';
    document.getElementById('match-name').textContent = 'Matching soon';
    document.getElementById('match-specialty-badge').textContent = specialtyLabel;
    document.getElementById('match-bio').textContent = '';
    document.getElementById('match-certs').textContent = '';
    unmatchedEl.style.display = 'block';
    return;
  }
  unmatchedEl.style.display = 'none';
  const instructor = result.instructor;
  const initials = instructor.name.split(' ').filter(Boolean).map(w => w[0].toUpperCase()).slice(0, 2).join('');
  document.getElementById('match-avatar').textContent = initials;
  document.getElementById('match-name').textContent = instructor.name;
  document.getElementById('match-specialty-badge').textContent = specialtyLabel;
  document.getElementById('match-bio').textContent = instructor.bio;
  document.getElementById('match-certs').textContent = isLessonRequest && result.distance_km != null
    ? `${instructor.certifications} · ~${result.distance_km} km away`
    : instructor.certifications;
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
    renderMatch(lessonRequest, false);
    goToScreen('match');
    return;
  } catch (err) {
    // No lesson request yet (404) — fall through and check for a booking.
  }
  try {
    const booking = await apiFetch('/api/customer/bookings/me');
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
