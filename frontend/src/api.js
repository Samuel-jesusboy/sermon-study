import { supabase } from './supabase';

export const API_BASE = (process.env.REACT_APP_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function authHeader() {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function req(path, options = {}) {
  const isForm = options.body instanceof FormData;
  const headers = { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...(await authHeader()), ...(options.headers || {}) };
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (e) {
    throw new Error('Cannot reach the Sermon Study server. Is the backend running?');
  }
  if (res.status === 401 && supabase) {
    await supabase.auth.signOut();
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = Array.isArray(err.detail) ? err.detail.map(d => d.msg).join('; ') : err.detail;
    throw new Error(detail || 'Request failed');
  }
  return res.json();
}

const post = (path, data) => req(path, { method: 'POST', body: JSON.stringify(data || {}) });
const patch = (path, data) => req(path, { method: 'PATCH', body: JSON.stringify(data || {}) });
const del = (path) => req(path, { method: 'DELETE' });
const qs = (params) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, v); });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const api = {
  config: () => req('/config'),

  // Sermons
  processSermon: (data) => post('/sermons/process', data),
  pasteTranscript: (data) => post('/sermons/paste', data),
  uploadSermon: (file, fields) => {
    const form = new FormData();
    form.append('file', file);
    Object.entries(fields || {}).forEach(([k, v]) => form.append(k, v ?? ''));
    return req('/sermons/upload', { method: 'POST', body: form });
  },
  processPlaylist: (data) => post('/sermons/playlist', data),
  listSermons: (params = {}) => req(`/sermons/list${qs({ limit: 100, ...params })}`),
  topics: () => req('/sermons/topics'),
  sermonsByBook: (book) => req(`/sermons/by-book/${encodeURIComponent(book)}`),
  getSermon: (id) => req(`/sermons/${id}`),
  updateSermon: (id, data) => patch(`/sermons/${id}`, data),
  exportMarkdown: (id) => req(`/sermons/${id}/markdown`),
  deleteSermon: (id) => del(`/sermons/${id}`),
  publicSermon: (id) => req(`/public/sermons/${id}`),

  // Jobs
  listJobs: (active = false) => req(`/jobs${active ? '?active=true' : ''}`),
  getJob: (id) => req(`/jobs/${id}`),
  retryJob: (id) => post(`/jobs/${id}/retry`),
  dismissJob: (id) => del(`/jobs/${id}`),

  // Bible
  getBibleVersions: () => req('/bible/versions'),
  getBibleBooks: (version = 'kjv') => req(`/bible/books?version=${version}`),
  getChapter: (book, chapter, version = 'kjv') => req(`/bible/chapter?book=${encodeURIComponent(book)}&chapter=${chapter}&version=${version}`),
  searchBible: (q, version = 'kjv') => req(`/bible/search?q=${encodeURIComponent(q)}&version=${version}`),
  lookupVerse: (ref, version = 'kjv') => req(`/bible/lookup?ref=${encodeURIComponent(ref)}&version=${version}`),

  // Ask
  ask: (data) => post('/ask/', data),
  explainVerse: (data) => post('/ask/explain-verse', data),

  // Churches
  listChurches: () => req('/churches/'),
  addChurch: (data) => post('/churches/', data),
  updateChurch: (id, data) => patch(`/churches/${id}`, data),
  deleteChurch: (id) => del(`/churches/${id}`),
  getChurchSermons: (id) => req(`/churches/${id}/sermons`),
  checkChurch: (id) => post(`/churches/${id}/check`),
  syncChurches: () => post('/churches/sync'),

  // Study guides
  generateGuide: (data) => post('/studyguide/generate', data),
  listGuides: () => req('/studyguide/list'),
  getGuide: (id) => req(`/studyguide/${id}`),
  deleteGuide: (id) => del(`/studyguide/${id}`),
};
