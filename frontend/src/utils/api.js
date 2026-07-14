/**
 * API client for Workout Viz backend.
 * All requests go through the Vite proxy → FastAPI on :8001.
 *
 * Auth: reads the session JWT from localStorage (key: volken_session_token),
 * injected there by the iOS WKWebView before the page loads.  On 401 the
 * native bridge is called so the iOS auth gate can re-appear.
 */

const BASE = '/api';
const TOKEN_KEY = 'volken_session_token';

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handleUnauthorized() {
  try {
    window.WorkoutVizNative?.unauthorized?.();
  } catch {
    // Running in browser dev — no native bridge; ignore.
  }
}

async function fetchJSON(url, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getOverview() {
  return fetchJSON(`${BASE}/stats/overview`);
}

export async function getActivities(params = {}) {
  const qs = new URLSearchParams();
  if (params.type) qs.set('type', params.type);
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);
  if (params.limit) qs.set('limit', params.limit);
  if (params.offset) qs.set('offset', params.offset);
  return fetchJSON(`${BASE}/activities?${qs.toString()}`);
}

export async function getActivity(id) {
  return fetchJSON(`${BASE}/activities/${id}`);
}

export async function getActivitySplits(id) {
  return fetchJSON(`${BASE}/activities/${id}/splits`);
}

export async function getActivitySummary(id) {
  return fetchJSON(`${BASE}/activities/${id}/summary`);
}

export async function getActivityFastestSegments(id) {
  return fetchJSON(`${BASE}/activities/${id}/fastest_segments`);
}

export async function getSwimLaps(id) {
  return fetchJSON(`${BASE}/activities/${id}/swim-laps`);
}

export async function getSimilarActivities(id, topN = 5) {
  return fetchJSON(`${BASE}/activities/${id}/similar?top_n=${topN}`);
}

export async function getTrends(params = {}) {
  const qs = new URLSearchParams();
  if (params.type) qs.set('type', params.type);
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);
  return fetchJSON(`${BASE}/stats/trends?${qs.toString()}`);
}

export async function getActivityTypes() {
  return fetchJSON(`${BASE}/activities/types`);
}

export async function getCalendar(months = 12) {
  return fetchJSON(`${BASE}/stats/calendar?months=${months}`);
}

export async function getAuthStatus() {
  return fetchJSON(`${BASE}/auth/status`);
}

export async function getAuthUrl() {
  return fetchJSON(`${BASE}/auth/strava/url`);
}

export async function syncActivities(deep = false) {
  const url = deep ? `${BASE}/activities/sync?deep=true` : `${BASE}/activities/sync`;
  return fetchJSON(url, { method: 'POST' });
}

export async function getSyncStatus() {
  return fetchJSON(`${BASE}/activities/sync/status`);
}

export async function startSplitsBackfill(params = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set('limit', params.limit);
  if (params.types) qs.set('types', params.types);
  const q = qs.toString();
  return fetchJSON(`${BASE}/activities/splits/sync${q ? '?' + q : ''}`, { method: 'POST' });
}

export async function getSplitsSyncStatus() {
  return fetchJSON(`${BASE}/activities/splits/sync/status`);
}

export async function getPcaData(type = 'Run') {
  return fetchJSON(`${BASE}/similarity/pca?type=${type}`);
}

export async function getBestSegmentsTrend(params = {}) {
  const qs = new URLSearchParams();
  if (params.type) qs.set('type', params.type);
  if (params.distance) qs.set('distance', params.distance);
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);
  return fetchJSON(`${BASE}/stats/best-segments?${qs.toString()}`);
}

export async function getActivityInsights(id) {
  return fetchJSON(`${BASE}/activities/${id}/insights`);
}

export async function getFitnessData(params = {}) {
  const qs = new URLSearchParams();
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);
  return fetchJSON(`${BASE}/stats/fitness?${qs.toString()}`);
}

export async function getReadiness() {
  return fetchJSON(`${BASE}/stats/readiness`);
}

export async function getReadinessHistory(days = 90) {
  return fetchJSON(`${BASE}/stats/readiness/history?days=${days}`);
}

export async function getCorrelations(days = 365) {
  return fetchJSON(`${BASE}/stats/correlations?days=${days}`);
}

export async function getWeeklyDigest() {
  return fetchJSON(`${BASE}/stats/digest`);
}

export async function getEfficiencyTrend(params = {}) {
  const qs = new URLSearchParams();
  if (params.type) qs.set('type', params.type);
  if (params.days) qs.set('days', params.days);
  return fetchJSON(`${BASE}/stats/efficiency?${qs.toString()}`);
}

export async function getRoutes(type = 'Run') {
  return fetchJSON(`${BASE}/routes?type=${type}`);
}

export async function getRoute(id) {
  return fetchJSON(`${BASE}/routes/${id}`);
}

export async function buildRoutes(type = 'Run') {
  return fetchJSON(`${BASE}/routes/build?type=${type}`, { method: 'POST' });
}

export async function renameRoute(id, name) {
  return fetchJSON(`${BASE}/routes/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function getRacePredictions(params = {}) {
  const qs = new URLSearchParams();
  if (params.type) qs.set('type', params.type);
  if (params.days) qs.set('days', params.days);
  return fetchJSON(`${BASE}/stats/predictions?${qs.toString()}`);
}

export async function getBlocks() {
  return fetchJSON(`${BASE}/blocks`);
}

export async function createBlock(body) {
  return fetchJSON(`${BASE}/blocks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function updateBlock(id, body) {
  return fetchJSON(`${BASE}/blocks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function deleteBlock(id) {
  return fetchJSON(`${BASE}/blocks/${id}`, { method: 'DELETE' });
}

export async function importAppleHealth(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/import/apple-health`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error('Unauthorized'); }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Import failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function getAppleHealthImportStatus() {
  return fetchJSON(`${BASE}/import/apple-health/status`);
}

export async function getRecentPRs(params = {}) {
  const qs = new URLSearchParams();
  if (params.since) qs.set('since', params.since);
  if (params.limit) qs.set('limit', params.limit);
  return fetchJSON(`${BASE}/activities/prs?${qs.toString()}`);
}

export async function getBestPRs() {
  return fetchJSON(`${BASE}/activities/prs/best`);
}

export async function getActivityComparison(id) {
  return fetchJSON(`${BASE}/activities/${id}/comparison`);
}

export async function getHealthSummary() {
  return fetchJSON(`${BASE}/health/summary`);
}

export async function getHealthMetric(metric, days = 90) {
  return fetchJSON(`${BASE}/health/metrics/${metric}?days=${days}`);
}
