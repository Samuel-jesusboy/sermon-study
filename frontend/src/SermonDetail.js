import React, { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api } from './api';
import { useApp } from './AppContext';
import SermonDocument from './SermonDocument';
import { money, tiersFor } from './modelInfo';

export function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}

const Label = ({ children, color = 'var(--gold)' }) => (
  <p className="mini-label" style={{ color }}>{children}</p>
);

// The YouTube player sits at the top; any timestamp in the notes seeks it.
function Player({ videoId, seek }) {
  if (!videoId) return null;
  const start = Math.max(0, Math.floor(seek?.seconds || 0));
  const src = `https://www.youtube-nocookie.com/embed/${videoId}?start=${start}${seek?.autoplay ? '&autoplay=1' : ''}&rel=0`;
  return (
    <div className="player">
      <iframe key={`${start}-${seek?.at || 0}`} src={src} title="Sermon video" allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />
    </div>
  );
}

function TimeLink({ seconds, onSeek }) {
  if (!(seconds > 0)) return null;
  return <button className="time-link" onClick={() => onSeek(seconds)}>▶ {fmtTime(seconds)}</button>;
}

export default function SermonDetail({ sermon: initial, onBack, onDelete, startAt, readOnly = false }) {
  const app = useApp();
  const [sermon, setSermon] = useState(initial);
  const [tab, setTab] = useState('document');
  const [seek, setSeek] = useState(() => ({ seconds: startAt ?? initial.sermon_start_seconds ?? 0, autoplay: startAt != null, at: 0 }));
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ title: initial.title || '', preacher: initial.preacher || '', church_name: initial.church_name || '',
    sermon_date: initial.sermon_date || '', series: initial.series || '', main_text: initial.main_text || '' });
  const outdated = !readOnly && (sermon.curation_version || 1) < 2;
  const top = useRef(null);
  const info = sermon.sermon_start_info || {};
  const group = info.small_group_guide || {};
  const hasGroup = group && (group.icebreaker || (group.discussion || []).length);
  const shareUrl = `${window.location.origin}/s/${sermon.id}`;

  useEffect(() => { setSermon(initial); }, [initial]);

  const onSeek = (seconds) => {
    if (!sermon.video_id) return;
    setSeek({ seconds, autoplay: true, at: Date.now() });
    top.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const save = async () => {
    try {
      const updated = await api.updateSermon(sermon.id, form);
      setSermon(s => ({ ...s, ...updated }));
      setEditing(false);
      toast.success('Saved');
    } catch (e) { toast.error(e.message); }
  };

  const [recuratePanel, setRecuratePanel] = useState(false);
  const [premium, setPremium] = useState(false);
  const tiers = app ? tiersFor(app.config, app.model) : {};

  const recurate = async () => {
    setRecuratePanel(false);
    try {
      const r = await api.recurate(sermon.id, { model: app?.model || undefined, premium });
      app?.trackJob(r.job);
      toast.success('Re-curating in the background. The new document opens when it is ready.');
    } catch (e) { toast.error(e.message); }
  };

  const toggleShare = async () => {
    try {
      const updated = await api.updateSermon(sermon.id, { is_public: !sermon.is_public });
      setSermon(s => ({ ...s, is_public: updated.is_public }));
      if (updated.is_public) {
        await navigator.clipboard?.writeText(shareUrl).catch(() => {});
        toast.success('Share link copied. Anyone with the link can read these notes.');
      } else toast('Sharing turned off');
    } catch (e) { toast.error(e.message); }
  };

  const whatsapp = () => {
    const text = `${sermon.title}\n${sermon.main_theme || ''}\n\nRead the full notes: ${shareUrl}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank', 'noopener');
  };

  const download = async () => {
    try {
      const { filename, markdown } = await api.exportMarkdown(sermon.id);
      const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown' }));
      const a = Object.assign(document.createElement('a'), { href: url, download: filename });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(e.message); }
  };

  const copyNotes = async () => {
    try {
      const { markdown } = await api.exportMarkdown(sermon.id);
      await navigator.clipboard.writeText(markdown);
      toast.success('Notes copied');
    } catch (e) { toast.error(e.message); }
  };

  const tabs = [['document', 'Document'], ['notes', 'Full notes'], ['verses', 'Verses'], ['study', 'Study'],
    ...(hasGroup ? [['group', 'Small group']] : []), ...((sermon.timed_chunks || []).length ? [['transcript', 'Transcript']] : [])];

  return (
    <div ref={top}>
      {onBack && <button className="btn btn-ghost btn-sm no-print" onClick={onBack} style={{ marginBottom: 12 }}>← Back</button>}
      <div className="sermon-detail">
        <Player videoId={sermon.video_id} seek={seek} />
        <div className="sermon-detail-header">
          <div className="sermon-meta">
            {sermon.church_name && <span className="badge badge-gold">{sermon.church_name}</span>}
            {sermon.preacher && <span className="badge badge-purple">{sermon.preacher}</span>}
            {info.sermon_start_time && sermon.video_id && (
              <button className="time-link" onClick={() => onSeek(sermon.sermon_start_seconds)}>
                Sermon starts at {info.sermon_start_time}{info.confidence && info.confidence !== 'manual' ? ` (${info.confidence} confidence)` : ''}
              </button>
            )}
          </div>
          {editing ? (
            <div className="edit-grid no-print">
              <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} placeholder="Title" />
              <input value={form.preacher} onChange={e => setForm(f => ({ ...f, preacher: e.target.value }))} placeholder="Preacher" />
              <input value={form.church_name} onChange={e => setForm(f => ({ ...f, church_name: e.target.value }))} placeholder="Church" />
              <div className="row-3">
                <label className="form-label">Date preached<input type="date" value={form.sermon_date || ''} onChange={e => setForm(f => ({ ...f, sermon_date: e.target.value }))} /></label>
                <label className="form-label">Series<input type="text" value={form.series} onChange={e => setForm(f => ({ ...f, series: e.target.value }))} placeholder="e.g. Spiritual Growth" /></label>
                <label className="form-label">Main text<input type="text" value={form.main_text} onChange={e => setForm(f => ({ ...f, main_text: e.target.value }))} placeholder="e.g. Ephesians 1:17-18" /></label>
              </div>
              <div className="btn-row"><button className="btn btn-primary btn-sm" onClick={save}>Save</button>
                <button className="btn btn-sm" onClick={() => setEditing(false)}>Cancel</button></div>
            </div>
          ) : (
            <h2 className="detail-title">{sermon.title}</h2>
          )}
          {sermon.main_theme && <p className="detail-theme">{sermon.main_theme}</p>}
          <p className="detail-summary">{sermon.summary}</p>
          {!readOnly && (Number(sermon.cost_usd) > 0 || sermon.model_used) && (
            <p className="soft cost-line">{sermon.model_used && <>Written by <code>{sermon.model_used}</code></>}
              {Number(sermon.cost_usd) > 0 && <> · AI cost {money(sermon.cost_usd)}</>}</p>
          )}
          {(sermon.topics || []).length > 0 && (
            <div className="chip-row" style={{ marginTop: 10 }}>{sermon.topics.map(t => <span key={t} className="badge badge-purple">{t}</span>)}</div>
          )}
          {!readOnly && (
            <div className="btn-row no-print" style={{ marginTop: 14 }}>
              <button className={`btn btn-sm ${sermon.is_public ? 'btn-gold' : ''}`} onClick={toggleShare}>
                {sermon.is_public ? 'Shared ✓' : 'Share link'}
              </button>
              {sermon.is_public && <button className="btn btn-sm" onClick={whatsapp}>WhatsApp</button>}
              <button className="btn btn-sm" onClick={copyNotes}>Copy notes</button>
              <button className="btn btn-sm" onClick={download}>Download .md</button>
              <button className="btn btn-sm" onClick={() => window.print()}>Print / PDF</button>
              <button className="btn btn-sm" onClick={() => setEditing(true)}>Edit</button>
              <button className="btn btn-sm" onClick={() => setRecuratePanel(p => !p)} title="Rewrite the document from the saved transcript">Re-curate</button>
              <button className="btn btn-sm btn-danger" onClick={() => onDelete(sermon.id)}>Delete</button>
            </div>
          )}
        </div>

        {recuratePanel && !readOnly && (
          <div className="recurate-panel no-print">
            <p className="body small" style={{ marginBottom: 8 }}>Rewrite this document from the saved transcript in the latest format. Title, date, series and sharing stay as they are.</p>
            {tiers.notes_premium && tiers.notes_premium !== tiers.notes && (
              <label className="check"><input type="checkbox" checked={premium} onChange={e => setPremium(e.target.checked)} />
                Premium quality (<code>{tiers.notes_premium}</code> instead of <code>{tiers.notes}</code>, about twice the cost)</label>
            )}
            <div className="btn-row"><button className="btn btn-primary btn-sm" onClick={recurate}>Re-curate now</button>
              <button className="btn btn-sm" onClick={() => setRecuratePanel(false)}>Cancel</button></div>
          </div>
        )}
        {outdated && (
          <div className="upgrade no-print">
            <span>This sermon was curated before the full documentation format.</span>
            <button className="btn btn-sm btn-gold" onClick={() => setRecuratePanel(true)}>Upgrade to the new format</button>
          </div>
        )}
        <div className="tabs-row no-print" style={{ margin: '1rem 1.25rem 0' }}>
          {tabs.map(([id, name]) => (
            <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{name}</button>
          ))}
        </div>

        <div className={`tab-panel print-me ${tab === 'document' ? '' : 'screen-hidden'}`}><SermonDocument sermon={sermon} onSeek={sermon.video_id ? onSeek : null} /></div>
        {tab === 'notes' && <div className="tab-panel"><Notes sermon={sermon} onSeek={onSeek} /></div>}
        {tab === 'verses' && <div className="tab-panel"><Verses sermon={sermon} onSeek={onSeek} /></div>}
        {tab === 'study' && <div className="tab-panel"><Study sermon={sermon} /></div>}
        {hasGroup && tab === 'group' && <div className="tab-panel"><SmallGroup guide={group} /></div>}
        {tab === 'transcript' && <Transcript sermon={sermon} onSeek={onSeek} />}
      </div>
    </div>
  );
}

function Notes({ sermon, onSeek }) {
  const intro = sermon.introduction || {};
  const concl = sermon.conclusion || {};
  return (
    <div>
      {(intro.opening || intro.context || intro.thesis) && (
        <div className="sermon-section">
          <h4>Introduction</h4>
          {intro.opening && <div className="block"><Label>Opening</Label><p className="body">{intro.opening}</p></div>}
          {intro.context && <div className="block"><Label>Context</Label><p className="body">{intro.context}</p></div>}
          {intro.thesis && <div className="callout purple"><Label color="var(--purple)">Thesis</Label><p className="body italic">{intro.thesis}</p></div>}
        </div>
      )}

      {(sermon.full_notes || []).map((section, i) => (
        <div className="sermon-section" key={i}>
          <div className="section-head">
            <div className="num">{section.section_number || i + 1}</div>
            <h4 className="section-name">{section.section_title}</h4>
            <span style={{ marginLeft: 'auto' }}><TimeLink seconds={section.start_seconds} onSeek={onSeek} /></span>
          </div>
          {section.full_teaching && <p className="body pre">{section.full_teaching}</p>}
          {(section.illustrations || []).map((ill, j) => (
            <div key={j} className="callout gold">
              <Label>Illustration: {ill.title}</Label>
              <p className="body">{ill.full_story}</p>
              {ill.spiritual_point && <p className="point">Point: {ill.spiritual_point}</p>}
            </div>
          ))}
          {(section.scriptures_in_this_section || []).map((v, j) => (
            <div key={j} className="scripture">
              <p className="ref">{v.reference}</p>
              {v.text_as_used && <p className="body italic">"{v.text_as_used}"</p>}
              {v.how_preacher_used_it && <p className="body small">{v.how_preacher_used_it}</p>}
            </div>
          ))}
          {(section.key_statements || []).map((q, j) => <blockquote key={j} className="statement">"{q}"</blockquote>)}
          {section.section_application && (
            <div className="callout green"><Label color="var(--green)">Application</Label><p className="body small">{section.section_application}</p></div>
          )}
        </div>
      ))}

      {(sermon.theological_depths || []).length > 0 && (
        <div className="sermon-section">
          <h4>Theological insights</h4>
          {sermon.theological_depths.map((t, i) => (
            <div key={i} className="callout purple"><p className="ref" style={{ color: 'var(--purple)' }}>{t.concept}</p><p className="body">{t.full_explanation}</p></div>
          ))}
        </div>
      )}

      {(sermon.notable_quotes || []).length > 0 && (
        <div className="sermon-section">
          <h4>Notable quotes</h4>
          {sermon.notable_quotes.map((q, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <blockquote className="quote">"{q.quote}"</blockquote>
              <p className="quote-context">{q.context} <TimeLink seconds={q.start_seconds} onSeek={onSeek} /></p>
            </div>
          ))}
        </div>
      )}

      {(concl.closing_argument || concl.call_to_action || concl.closing_prayer_or_charge) && (
        <div className="sermon-section">
          <h4>Conclusion</h4>
          {concl.closing_argument && <div className="block"><Label color="var(--text-soft)">Closing argument</Label><p className="body">{concl.closing_argument}</p></div>}
          {concl.call_to_action && <div className="callout purple"><Label color="var(--purple)">Call to action</Label><p className="body">{concl.call_to_action}</p></div>}
          {concl.closing_prayer_or_charge && <p className="body italic">{concl.closing_prayer_or_charge}</p>}
        </div>
      )}

      {sermon.sermon_character && (
        <div className="sermon-section"><h4>About this message</h4><p className="body">{sermon.sermon_character}</p></div>
      )}
    </div>
  );
}

function Verses({ sermon, onSeek }) {
  const verses = sermon.all_bible_verses || [];
  return (
    <div className="sermon-section">
      <h4>Bible verses referenced</h4>
      <div className="chip-row" style={{ marginBottom: 16 }}>{verses.map((v, i) => <span className="verse-pill" key={i}>{v.reference}</span>)}</div>
      {verses.map((v, i) => (
        <div key={i} className="verse-row">
          <p className="ref">{v.reference} <TimeLink seconds={v.start_seconds} onSeek={onSeek} /></p>
          {v.text_quoted && <p className="body italic">"{v.text_quoted}"</p>}
          {v.sermon_context && <p className="body small">{v.sermon_context}</p>}
          {(v.cross_references || []).length > 0 && <p className="soft">See also: {v.cross_references.join(', ')}</p>}
        </div>
      ))}
    </div>
  );
}

function Study({ sermon }) {
  return (
    <div>
      {(sermon.practical_applications || []).length > 0 && (
        <div className="sermon-section">
          <h4>Practical applications</h4>
          {sermon.practical_applications.map((a, i) => (
            <div key={i} className="callout green">
              <p className="ref" style={{ color: 'var(--green)' }}>✓ {a.application || a}</p>
              {a.why_it_matters && <p className="body small">{a.why_it_matters}</p>}
              {a.how_to_do_it && <p className="body small">How: {a.how_to_do_it}</p>}
            </div>
          ))}
        </div>
      )}
      {(sermon.prayer_points || []).length > 0 && (
        <div className="sermon-section">
          <h4>Prayer points</h4>
          {sermon.prayer_points.map((p, i) => (
            <div key={i} className="verse-row">
              <p className="body">🙏 {p.point || p}</p>
              {p.scripture_basis && <p className="soft" style={{ color: 'var(--gold-deep)' }}>Pray from: {p.scripture_basis}</p>}
            </div>
          ))}
        </div>
      )}
      {(sermon.study_questions || []).length > 0 && (
        <div className="sermon-section">
          <h4>Study questions</h4>
          {sermon.study_questions.map((q, i) => (
            <div key={i} className="callout cream">
              <p className="body" style={{ fontWeight: 500 }}>{i + 1}. {q.question || q}</p>
              {q.what_to_think_about && <p className="soft">{q.what_to_think_about}</p>}
            </div>
          ))}
        </div>
      )}
      {sermon.weekly_challenge && (
        <div className="sermon-section"><h4>This week's challenge</h4><div className="callout gold"><p className="body" style={{ color: 'var(--gold-deep)', fontWeight: 500 }}>{sermon.weekly_challenge}</p></div></div>
      )}
      {(sermon.related_topics || []).length > 0 && (
        <div className="sermon-section"><h4>Topics for further study</h4>
          <div className="chip-row">{sermon.related_topics.map((t, i) => <span key={i} className="badge badge-purple">{t}</span>)}</div></div>
      )}
    </div>
  );
}

function SmallGroup({ guide }) {
  return (
    <div className="sermon-section">
      <h4>Small group / house fellowship guide</h4>
      {guide.icebreaker && <div className="block"><Label>Icebreaker</Label><p className="body">{guide.icebreaker}</p></div>}
      {(guide.discussion || []).length > 0 && (
        <div className="block"><Label>Discussion</Label>
          <ol className="body" style={{ paddingLeft: 20 }}>{guide.discussion.map((q, i) => <li key={i} style={{ marginBottom: 6 }}>{q}</li>)}</ol></div>
      )}
      {guide.activity && <div className="callout green"><Label color="var(--green)">Activity</Label><p className="body small">{guide.activity}</p></div>}
      {guide.closing_prayer && <div className="callout purple"><Label color="var(--purple)">Closing prayer</Label><p className="body italic">{guide.closing_prayer}</p></div>}
    </div>
  );
}

function Transcript({ sermon, onSeek }) {
  const info = sermon.sermon_start_info || {};
  return (
    <div className="sermon-section">
      <h4>Transcript</h4>
      {info.sermon_start_time && (
        <p className="notice">Showing from the sermon start at {info.sermon_start_time}{info.reason ? ` · ${info.reason}` : ''}
          {info.transcript_method === 'whisper' ? ' · transcribed from audio' : ''}</p>
      )}
      {(sermon.timed_chunks || []).map((c, i) => (
        <div className="timed-chunk" key={i}>
          {sermon.video_id ? <button className="chunk-time" onClick={() => onSeek(c.seconds)}>{c.time}</button>
            : <span className="chunk-time">{c.time}</span>}
          <p className="chunk-text">{c.text}</p>
        </div>
      ))}
    </div>
  );
}
