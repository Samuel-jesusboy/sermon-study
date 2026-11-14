import React, { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { format } from 'date-fns';
import { api } from './api';
import { useApp } from './AppContext';
import ModelSelector from './ModelSelector';
import SermonDetail from './SermonDetail';

const EMPTY = { url: '', church_name: '', preacher: '', start_time: '', text: '', title: '', file: null, sermon_date: '', series: '', main_text: '' };

function AddSermon({ onDone }) {
  const { model, config, trackJob, loadJobs, openSermon } = useApp();
  const [type, setType] = useState('single');
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    const common = { model: model || undefined, church_name: form.church_name, preacher: form.preacher,
      sermon_date: form.sermon_date || null, series: form.series, main_text: form.main_text };
    setBusy(true);
    try {
      if (type === 'single') {
        if (!form.url.trim()) throw new Error('Paste a YouTube link');
        const r = await api.processSermon({ ...common, url: form.url, sermon_start_time: form.start_time || null });
        if (r.existing_sermon_id) {
          toast(t => (<span>That sermon is already in your library. <button className="link-btn" onClick={() => { openSermon(r.existing_sermon_id); toast.dismiss(t.id); }}>Open it</button></span>));
        } else { trackJob(r.job); toast.success('Processing in the background. You can keep using the app.'); }
      } else if (type === 'playlist') {
        if (!form.url.trim()) throw new Error('Paste a YouTube playlist link');
        const r = await api.processPlaylist({ model: common.model, church_name: form.church_name, series: form.series, playlist_url: form.url });
        toast.success(`Queued ${r.queued} sermon${r.queued === 1 ? '' : 's'}${r.skipped_existing ? ` (${r.skipped_existing} already in your library)` : ''}`);
        loadJobs();
      } else if (type === 'upload') {
        if (!form.file) throw new Error('Choose an audio or video file');
        const r = await api.uploadSermon(form.file, { ...common, model: model || '', sermon_date: form.sermon_date || '', sermon_start_time: form.start_time });
        trackJob(r.job); toast.success('Uploaded. Transcribing in the background.');
      } else {
        if (form.text.trim().length < 200) throw new Error('Paste the full transcript (at least a few paragraphs)');
        const r = await api.pasteTranscript({ ...common, transcript_text: form.text, title: form.title, sermon_start_time: form.start_time || null });
        trackJob(r.job); toast.success('Processing in the background.');
      }
      setForm(EMPTY);
      onDone();
    } catch (e) { toast.error(e.message); }
    setBusy(false);
  };

  return (
    <div className="card">
      <p className="card-title">Add a sermon</p>
      <div className="tabs-row" style={{ marginBottom: 16 }}>
        {[['single', 'YouTube video'], ['playlist', 'Playlist'], ['upload', 'Upload audio'], ['paste', 'Paste transcript']].map(([id, name]) => (
          <button key={id} className={`tab-btn ${type === id ? 'active' : ''}`} onClick={() => setType(id)}>{name}</button>
        ))}
      </div>

      {(type === 'single' || type === 'playlist') && (
        <div className="form-group">
          <label className="form-label">YouTube {type === 'playlist' ? 'playlist' : 'video'} link</label>
          <input type="url" value={form.url} onChange={set('url')}
            placeholder={type === 'playlist' ? 'https://youtube.com/playlist?list=...' : 'https://youtube.com/watch?v=...'} />
        </div>
      )}
      {type === 'upload' && (
        <div className="form-group">
          <label className="form-label">Audio or video file (up to {config.max_upload_mb || 200} MB)</label>
          <input type="file" accept="audio/*,video/*" onChange={e => setForm(f => ({ ...f, file: e.target.files[0] || null }))} />
          {!config.audio_transcription && <p className="hint warn">Audio transcription needs a Groq or OpenAI key on the server.</p>}
        </div>
      )}
      {type === 'paste' && (
        <>
          <div className="form-group">
            <label className="form-label">Title <span className="opt">(optional)</span></label>
            <input type="text" value={form.title} onChange={set('title')} placeholder="The AI will name it if you leave this blank" />
          </div>
          <div className="form-group">
            <label className="form-label">Transcript</label>
            <textarea value={form.text} onChange={set('text')} style={{ minHeight: 160 }}
              placeholder={'Paste the transcript. Lines that start with a time like 12:30 keep their timestamps.'} />
          </div>
        </>
      )}

      <div className="row-2">
        <div className="form-group">
          <label className="form-label">Church <span className="opt">(optional)</span></label>
          <input type="text" value={form.church_name} onChange={set('church_name')} placeholder="Filled from the YouTube channel if blank" />
        </div>
        {type !== 'playlist' && (
          <div className="form-group">
            <label className="form-label">Preacher <span className="opt">(optional)</span></label>
            <input type="text" value={form.preacher} onChange={set('preacher')} placeholder="e.g. Pastor Sam Adeyemi" />
          </div>
        )}
      </div>
      <div className="row-3">
        {type !== 'playlist' && (
          <div className="form-group">
            <label className="form-label">Date preached <span className="opt">(optional)</span></label>
            <input type="date" value={form.sermon_date} onChange={set('sermon_date')} />
          </div>
        )}
        <div className="form-group">
          <label className="form-label">Series <span className="opt">(optional)</span></label>
          <input type="text" value={form.series} onChange={set('series')} placeholder="e.g. Spiritual Growth" />
        </div>
        {type !== 'playlist' && (
          <div className="form-group">
            <label className="form-label">Main text <span className="opt">(optional)</span></label>
            <input type="text" value={form.main_text} onChange={set('main_text')} placeholder="e.g. Ephesians 1:17-18" />
          </div>
        )}
      </div>
      {type !== 'playlist' && (
        <div className="form-group">
          <label className="form-label">Sermon start time <span className="opt">(optional, auto-detected if blank)</span></label>
          <input type="text" value={form.start_time} onChange={set('start_time')} placeholder="e.g. 14:32" style={{ maxWidth: 200 }} />
        </div>
      )}

      <div className="form-foot">
        <ModelSelector />
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          {busy ? <><span className="spinner small light" /> Sending…</> : type === 'playlist' ? 'Process playlist' : 'Process sermon'}
        </button>
      </div>
      <p className="hint">Full notes take 1 to 3 minutes. Progress shows at the top of the screen, and you can keep using the app.</p>
    </div>
  );
}

export default function SermonsTab() {
  const { library, refreshLibrary, openRequest, clearOpenRequest } = useApp();
  const [mode, setMode] = useState('list');
  const [sermons, setSermons] = useState([]);
  const [index, setIndex] = useState({ topics: [], books: [], churches: [], series: [] });
  const [filter, setFilter] = useState({ q: '', topic: '', church: '', book: '', series: '' });
  const [selected, setSelected] = useState(null);
  const [startAt, setStartAt] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchSermons = useCallback(async () => {
    setLoading(true);
    try {
      const data = filter.book ? await api.sermonsByBook(filter.book)
        : await api.listSermons({ q: filter.q, topic: filter.topic, church: filter.church, series: filter.series });
      setSermons(data);
    } catch (e) { toast.error('Could not load sermons: ' + e.message); }
    setLoading(false);
  }, [filter]);

  useEffect(() => { const t = setTimeout(fetchSermons, filter.q ? 300 : 0); return () => clearTimeout(t); }, [fetchSermons, library, filter.q]);
  useEffect(() => { api.topics().then(setIndex).catch(() => {}); }, [library]);

  const openSermon = useCallback(async (id, seconds = null) => {
    setLoading(true);
    try { const full = await api.getSermon(id); setSelected(full); setStartAt(seconds); setMode('detail'); window.scrollTo(0, 0); }
    catch (e) { toast.error(e.message); }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (openRequest) { openSermon(openRequest.sermonId, openRequest.seconds); clearOpenRequest(); }
  }, [openRequest, openSermon, clearOpenRequest]);

  const deleteSermon = async (id) => {
    if (!window.confirm('Delete this sermon and its notes?')) return;
    try { await api.deleteSermon(id); toast.success('Deleted'); setMode('list'); refreshLibrary(); }
    catch (e) { toast.error(e.message); }
  };

  const pick = (key, value) => setFilter(f => ({ q: f.q, topic: '', church: '', book: '', series: '', [key]: f[key] === value ? '' : value }));
  const anyFilter = filter.q || filter.topic || filter.church || filter.book || filter.series;

  if (mode === 'detail' && selected) {
    return <SermonDetail sermon={selected} startAt={startAt} onBack={() => setMode('list')} onDelete={deleteSermon} />;
  }

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Sermons</h2>
        <button className="btn btn-primary btn-sm" onClick={() => setMode(mode === 'add' ? 'list' : 'add')}>
          {mode === 'add' ? '← Back to library' : '+ Add sermon'}
        </button>
      </div>

      {mode === 'add' && <AddSermon onDone={() => setMode('list')} />}

      {mode === 'list' && (
        <>
          <input type="text" className="search" value={filter.q} placeholder="Search sermons, including what was said…"
            onChange={e => setFilter(f => ({ ...f, q: e.target.value, book: '' }))} />
          {(index.topics.length > 0 || index.books.length > 0) && (
            <div className="browse">
              {index.topics.length > 0 && <div className="chip-row">
                <span className="chip-label">Topics</span>
                {index.topics.slice(0, 18).map(t => (
                  <button key={t.name} className={`chip ${filter.topic === t.name ? 'on' : ''}`} onClick={() => pick('topic', t.name)}>{t.name} <small>{t.count}</small></button>
                ))}
              </div>}
              {index.books.length > 0 && <div className="chip-row">
                <span className="chip-label">Books</span>
                {index.books.slice(0, 14).map(b => (
                  <button key={b.name} className={`chip ${filter.book === b.name ? 'on' : ''}`} onClick={() => pick('book', b.name)}>{b.name} <small>{b.count}</small></button>
                ))}
              </div>}
              {(index.series || []).length > 0 && <div className="chip-row">
                <span className="chip-label">Series</span>
                {index.series.map(c => (
                  <button key={c.name} className={`chip ${filter.series === c.name ? 'on' : ''}`} onClick={() => pick('series', c.name)}>{c.name} <small>{c.count}</small></button>
                ))}
              </div>}
              {index.churches.length > 1 && <div className="chip-row">
                <span className="chip-label">Churches</span>
                {index.churches.map(c => (
                  <button key={c.name} className={`chip ${filter.church === c.name ? 'on' : ''}`} onClick={() => pick('church', c.name)}>{c.name} <small>{c.count}</small></button>
                ))}
              </div>}
            </div>
          )}
          {anyFilter && <button className="link-btn" style={{ marginBottom: 10 }} onClick={() => setFilter({ q: '', topic: '', church: '', book: '', series: '' })}>Clear filters</button>}

          {loading ? (
            <div className="loading"><div className="spinner" /> Loading sermons…</div>
          ) : sermons.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📺</div>
              <p>{anyFilter ? 'No sermons match.' : <>No sermons yet.<br />Add a YouTube link, upload a recording, or paste a transcript to start your library.</>}</p>
              {!anyFilter && <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={() => setMode('add')}>Add your first sermon</button>}
            </div>
          ) : sermons.map(s => (
            <div className="sermon-card" key={s.id} onClick={() => openSermon(s.id)}>
              <div className="sermon-meta">
                {s.church_name && <span className="badge badge-gold">{s.church_name}</span>}
                {s.preacher && <span className="soft">{s.preacher}</span>}
                {s.series && <span className="badge badge-purple">{s.series}</span>}
                {s.is_public && <span className="badge badge-green">Shared</span>}
                <span className="soft" style={{ marginLeft: 'auto' }}>{format(new Date(s.sermon_date ? `${s.sermon_date}T12:00:00` : s.created_at), 'MMM d, yyyy')}</span>
              </div>
              <h3>{s.title}</h3>
              {s.main_text && <p className="soft" style={{ marginBottom: 4 }}>{s.main_text}</p>}
              <p>{s.central_message || s.summary}</p>
              {s.transcript_match && (
                <div className="said" onClick={e => { e.stopPropagation(); openSermon(s.id, s.transcript_match.seconds); }}>
                  <span className="time-link">Said at {s.transcript_match.time}</span> <span>{s.transcript_match.excerpt}</span>
                </div>
              )}
              {s.matching_verses && <p className="soft" style={{ marginTop: 6 }}>Verses: {s.matching_verses.slice(0, 6).join(', ')}</p>}
              {(s.topics || []).length > 0 && <div className="chip-row" style={{ marginTop: 8 }}>{s.topics.slice(0, 5).map(t => <span key={t} className="badge badge-purple">{t}</span>)}</div>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
