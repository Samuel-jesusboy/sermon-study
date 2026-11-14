import React, { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { formatDistanceToNow } from 'date-fns';
import { api } from './api';
import { useApp } from './AppContext';

// Suggestions to add in one tap. They're only saved when you add them.
const SUGGESTED = [
  { name: 'COZA', youtube_channel_url: 'https://www.youtube.com/@COZALive', description: 'Commonwealth of Zion Assembly, Abuja' },
  { name: 'House On The Rock', youtube_channel_url: 'https://www.youtube.com/@HouseOnTheRockChurch', description: 'Pastor Paul Adefarasin, Lagos' },
  { name: 'Elevation Church', youtube_channel_url: 'https://www.youtube.com/@ElevationChurch', description: 'Steven Furtick' },
  { name: 'T.D. Jakes', youtube_channel_url: 'https://www.youtube.com/@TDJakes', description: 'The Potter’s House' },
];

const EMPTY = { name: '', youtube_channel_url: '', description: '', playlist_url: '', auto_import: false };

export default function ChurchesTab() {
  const { loadJobs, refreshLibrary } = useApp();
  const [churches, setChurches] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const fetchChurches = useCallback(async () => {
    try { setChurches(await api.listChurches()); } catch (e) { toast.error(e.message); }
    setLoading(false);
  }, []);
  useEffect(() => { fetchChurches(); }, [fetchChurches]);

  const add = async (data) => {
    if (!data.name.trim() || !data.youtube_channel_url.trim()) return toast.error('Name and channel link are required');
    setBusy('add');
    try { await api.addChurch(data); toast.success(`${data.name} added`); setForm(EMPTY); setShowAdd(false); fetchChurches(); }
    catch (e) { toast.error(e.message); }
    setBusy('');
  };

  const toggleAuto = async (c) => {
    try {
      await api.updateChurch(c.id, { auto_import: !c.auto_import });
      setChurches(cs => cs.map(x => x.id === c.id ? { ...x, auto_import: !c.auto_import } : x));
      toast(!c.auto_import ? 'New sermons will be added automatically when you open the app' : 'Auto-import off');
    } catch (e) { toast.error(e.message); }
  };

  const check = async (c) => {
    setBusy(c.id);
    try {
      const r = await api.checkChurch(c.id);
      if (r.queued) { toast.success(`Processing ${r.queued} new sermon${r.queued > 1 ? 's' : ''} from ${c.name}`); loadJobs(); }
      else toast(`No new sermons from ${c.name} (${r.already_in_library} already in your library)`);
      fetchChurches();
    } catch (e) { toast.error(e.message); }
    setBusy('');
  };

  const remove = async (c) => {
    if (!window.confirm(`Remove ${c.name}? Its sermons stay in your library.`)) return;
    try { await api.deleteChurch(c.id); fetchChurches(); refreshLibrary(); } catch (e) { toast.error(e.message); }
  };

  const suggestions = SUGGESTED.filter(s => !churches.some(c => c.youtube_channel_url.toLowerCase() === s.youtube_channel_url.toLowerCase()));

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Churches</h2>
        <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(s => !s)}>{showAdd ? '← Back' : '+ Add church'}</button>
      </div>
      <p className="lead">Save the churches you follow. Pull in their latest sermons with one tap, or turn on auto-import to add new ones whenever you open the app.</p>

      {showAdd && (
        <div className="card">
          <p className="card-title">Add a church</p>
          <div className="form-group"><label className="form-label">Church name</label>
            <input type="text" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Daystar Christian Centre" /></div>
          <div className="form-group"><label className="form-label">YouTube channel link</label>
            <input type="url" value={form.youtube_channel_url} onChange={e => setForm(f => ({ ...f, youtube_channel_url: e.target.value }))} placeholder="https://youtube.com/@..." /></div>
          <div className="form-group"><label className="form-label">Description <span className="opt">(optional)</span></label>
            <input type="text" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="e.g. Pastor Sam Adeyemi, Lagos" /></div>
          <div className="form-group"><label className="form-label">Sermons-only playlist <span className="opt">(optional, used instead of the whole channel)</span></label>
            <input type="url" value={form.playlist_url} onChange={e => setForm(f => ({ ...f, playlist_url: e.target.value }))} placeholder="https://youtube.com/playlist?list=..." /></div>
          <label className="check"><input type="checkbox" checked={form.auto_import} onChange={e => setForm(f => ({ ...f, auto_import: e.target.checked }))} /> Auto-import new sermons</label>
          <div className="btn-row"><button className="btn btn-primary" onClick={() => add(form)} disabled={busy === 'add'}>{busy === 'add' ? 'Adding…' : 'Add church'}</button></div>
        </div>
      )}

      <div className="card">
        {loading ? <div className="loading"><div className="spinner" /> Loading…</div>
          : churches.length === 0 ? <p className="soft">No churches yet. Add one above or pick a suggestion below.</p>
          : churches.map(c => (
            <div className="church-row" key={c.id}>
              <div className="church-icon"><svg width="16" height="16" viewBox="0 0 16 16" fill="white"><path d="M6.5 11.5l5-3.5-5-3.5v7z" /></svg></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p className="church-name">{c.name}</p>
                <p className="soft">{[c.description, `${c.sermon_count || 0} sermon${c.sermon_count === 1 ? '' : 's'}`,
                  c.last_checked_at && `checked ${formatDistanceToNow(new Date(c.last_checked_at))} ago`].filter(Boolean).join(' · ')}</p>
                <label className="check small"><input type="checkbox" checked={!!c.auto_import} onChange={() => toggleAuto(c)} /> Auto-import</label>
              </div>
              <div className="church-actions">
                <button className="btn btn-sm btn-gold" onClick={() => check(c)} disabled={busy === c.id}>{busy === c.id ? 'Checking…' : 'Get latest'}</button>
                <a href={c.youtube_channel_url} target="_blank" rel="noopener noreferrer" className="btn btn-sm">Visit ↗</a>
                <button className="btn btn-sm btn-danger" onClick={() => remove(c)} aria-label={`Remove ${c.name}`}>×</button>
              </div>
            </div>
          ))}
      </div>

      {suggestions.length > 0 && (
        <div className="card">
          <p className="card-title">Suggestions</p>
          {suggestions.map(s => (
            <div className="church-row" key={s.youtube_channel_url}>
              <div style={{ flex: 1 }}><p className="church-name">{s.name}</p><p className="soft">{s.description}</p></div>
              <button className="btn btn-sm" onClick={() => add({ ...EMPTY, ...s })}>+ Add</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
