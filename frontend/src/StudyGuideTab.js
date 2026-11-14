import React, { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import toast from 'react-hot-toast';
import { api } from './api';
import { useApp } from './AppContext';
import ModelSelector from './ModelSelector';

export default function StudyGuideTab() {
  const { model, library } = useApp();
  const [guides, setGuides] = useState([]);
  const [selected, setSelected] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [weeks, setWeeks] = useState(4);
  const [theme, setTheme] = useState('');
  const [audience, setAudience] = useState('personal');
  const [loading, setLoading] = useState(true);

  const fetchGuides = useCallback(async () => {
    try { setGuides(await api.listGuides()); } catch (e) { /* shown as empty */ }
    setLoading(false);
  }, []);
  useEffect(() => { fetchGuides(); }, [fetchGuides, library]);

  const generate = async () => {
    setGenerating(true);
    try {
      const data = await api.generateGuide({ weeks, theme, audience, model: model || undefined });
      setSelected({ ...data, content: data.guide });
      toast.success('Study guide ready');
      fetchGuides();
    } catch (e) { toast.error(e.message); }
    setGenerating(false);
  };

  const open = async (g) => {
    try { setSelected(await api.getGuide(g.id)); window.scrollTo(0, 0); } catch (e) { toast.error(e.message); }
  };

  const remove = async (g) => {
    if (!window.confirm('Delete this study guide?')) return;
    try { await api.deleteGuide(g.id); fetchGuides(); } catch (e) { toast.error(e.message); }
  };

  const copy = async () => { await navigator.clipboard.writeText(selected.content); toast.success('Copied'); };
  const download = () => {
    const url = URL.createObjectURL(new Blob([selected.content], { type: 'text/markdown' }));
    Object.assign(document.createElement('a'), { href: url, download: `study-guide-${selected.weeks}-weeks.md` }).click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Study guide</h2>
        <ModelSelector />
      </div>

      {!selected && (
        <div className="card">
          <p className="card-title">Build a study guide from your sermons</p>
          <div className="row-3">
            <div className="form-group"><label className="form-label">Length</label>
              <select value={weeks} onChange={e => setWeeks(Number(e.target.value))}>{[1, 2, 4, 6, 8, 12].map(w => <option key={w} value={w}>{w} week{w > 1 ? 's' : ''}</option>)}</select></div>
            <div className="form-group"><label className="form-label">For</label>
              <select value={audience} onChange={e => setAudience(e.target.value)}>
                <option value="personal">My daily devotions</option>
                <option value="small_group">A small group / house fellowship</option>
                <option value="family">Family devotions</option>
              </select></div>
            <div className="form-group"><label className="form-label">Theme <span className="opt">(optional)</span></label>
              <input type="text" value={theme} onChange={e => setTheme(e.target.value)} placeholder="e.g. Faith, Prayer, Purpose" /></div>
          </div>
          <button className="btn btn-gold" onClick={generate} disabled={generating}>
            {generating ? <><span className="spinner small light" /> Building your guide…</> : 'Generate study guide'}
          </button>
          {generating && <p className="hint">Reading your sermons and writing a {weeks}-week plan. This takes about a minute.</p>}
        </div>
      )}

      {selected && (
        <div className="card">
          <div className="sermon-meta no-print" style={{ marginBottom: 14 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>← All guides</button>
            <span className="badge badge-gold">{selected.sermons_used || selected.sermons_count} sermons</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              <button className="btn btn-sm" onClick={copy}>Copy</button>
              <button className="btn btn-sm" onClick={download}>Download</button>
              <button className="btn btn-sm" onClick={() => window.print()}>Print / PDF</button>
            </span>
          </div>
          <h3 className="detail-title" style={{ fontSize: 20 }}>{selected.weeks}-week study guide{selected.theme ? `: ${selected.theme}` : ''}</h3>
          <div className="markdown guide"><ReactMarkdown>{selected.content || selected.guide || ''}</ReactMarkdown></div>
        </div>
      )}

      {!selected && (loading ? <div className="loading"><div className="spinner" /></div> : guides.length > 0 ? (
        <div className="card">
          <p className="card-title">Your guides</p>
          {guides.map(g => (
            <div key={g.id} className="list-row">
              <div style={{ flex: 1, cursor: 'pointer' }} onClick={() => open(g)}>
                <p className="church-name">{g.weeks}-week guide{g.theme ? `: ${g.theme}` : ''}</p>
                <p className="soft">{g.sermons_count} sermons · {new Date(g.created_at).toLocaleDateString()}</p>
              </div>
              <button className="btn btn-sm btn-danger" onClick={() => remove(g)} aria-label="Delete guide">×</button>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state"><div className="icon">📚</div><p>Add a few sermons first, then build a guide from them.</p></div>
      ))}
    </div>
  );
}
