import React, { useEffect, useState } from 'react';
import { api } from './api';
import { useApp } from './AppContext';
import { money, tiersFor } from './modelInfo';

const JOBS = [
  ['notes', 'Sermon documents', 'The main product: full curated notes'],
  ['notes_premium', 'Premium documents', 'When you tick "Premium quality"'],
  ['guide', 'Study guides', 'Multi-week plans from your sermons'],
  ['ask', 'Ask', 'Answers from your library'],
  ['verse', 'Explain a verse', 'Short explanations'],
  ['start', 'Finding the sermon start', 'Skips worship and announcements'],
];

export default function UsageTab() {
  const { config, model, openSermon } = useApp();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setData(null);
    api.usage(days).then(setData).catch(e => setError(e.message));
  }, [days]);

  const tiers = tiersFor(config, model);
  const maxDay = Math.max(0.0001, ...((data?.by_day || []).map(d => d.cost)));

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Usage and cost</h2>
        <select value={days} onChange={e => setDays(Number(e.target.value))} style={{ width: 'auto' }}>
          <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
        </select>
      </div>

      {error && <p className="notice" style={{ background: 'var(--rose-light, #fde8e8)', color: 'var(--rose)' }}>{error}</p>}
      {!data && !error && <div className="loading"><div className="spinner" /> Loading usage…</div>}

      {data && (
        <>
          <div className="stat-row">
            <div className="stat"><p className="stat-label">This month</p><p className="stat-value">{money(data.month_total)}</p></div>
            <div className="stat"><p className="stat-label">Last {days} days</p><p className="stat-value">{money(data.window_total)}</p></div>
            <div className="stat"><p className="stat-label">Average per sermon</p><p className="stat-value">{data.avg_cost_per_sermon == null ? '–' : money(data.avg_cost_per_sermon)}</p></div>
            <div className="stat"><p className="stat-label">AI calls</p><p className="stat-value">{data.calls}</p></div>
          </div>
          <p className="hint" style={{ marginTop: -6, marginBottom: 14 }}>Estimates from each provider's list prices. Your provider's invoice is the final word.
            {data.unpriced_calls > 0 && ` ${data.unpriced_calls} call(s) used a model with no price on file.`}</p>

          {data.by_day.length > 0 && (
            <div className="card">
              <p className="card-title">Spend by day</p>
              <div className="day-bars">
                {data.by_day.map(d => (
                  <div key={d.date} className="day-bar" title={`${d.date}: ${money(d.cost)}`}>
                    <div style={{ height: `${Math.max(3, (d.cost / maxDay) * 100)}%` }} />
                    <span>{d.date.slice(8)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="row-2 usage-grid">
            <div className="card">
              <p className="card-title">By job</p>
              {data.by_task.length === 0 ? <p className="soft">No AI usage yet.</p> : (
                <table className="doc-table"><tbody>
                  {data.by_task.map(t => <tr key={t.task}><th>{t.label}</th><td>{money(t.cost)} <span className="soft">· {t.calls} call{t.calls === 1 ? '' : 's'}</span></td></tr>)}
                </tbody></table>
              )}
            </div>
            <div className="card">
              <p className="card-title">By model</p>
              {data.by_model.length === 0 ? <p className="soft">No AI usage yet.</p> : (
                <table className="doc-table"><tbody>
                  {data.by_model.map(m => <tr key={m.model}><th><code>{m.model}</code></th><td>{money(m.cost)} <span className="soft">· {m.audio_minutes > 0 ? `${m.audio_minutes} min of audio` : `${(m.tokens / 1000).toFixed(0)}K tokens`}</span></td></tr>)}
                </tbody></table>
              )}
            </div>
          </div>

          {data.recent_sermons.length > 0 && (
            <div className="card">
              <p className="card-title">Recent sermons</p>
              {data.recent_sermons.map(s => (
                <div className="list-row" key={s.id} style={{ cursor: 'pointer' }} onClick={() => openSermon(s.id)}>
                  <div style={{ flex: 1 }}><p className="church-name">{s.title}</p>
                    <p className="soft">{Object.values(s.models_used || {}).filter((v, i, a) => a.indexOf(v) === i).join(', ')}</p></div>
                  <strong>{money(s.cost_usd)}</strong>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div className="card">
        <p className="card-title">Which model does what</p>
        <p className="hint" style={{ marginTop: 0, marginBottom: 10 }}>Each job uses the model that fits it, so frequent simple work doesn't run on the most expensive model. Change these in <code>backend/.env</code>.</p>
        <table className="doc-table"><tbody>
          {JOBS.map(([id, name, why]) => (
            <tr key={id}><th>{name}<div className="soft" style={{ fontWeight: 400 }}>{why}</div></th><td><code>{tiers[id] || '–'}</code></td></tr>
          ))}
          {config.embedding_model && <tr><th>Search indexing<div className="soft" style={{ fontWeight: 400 }}>Semantic search for Ask</div></th><td><code>{config.embedding_model}</code></td></tr>}
          {config.transcription_model && <tr><th>Audio transcription<div className="soft" style={{ fontWeight: 400 }}>Uploads, and videos without captions</div></th><td><code>{config.transcription_model}</code></td></tr>}
        </tbody></table>
      </div>
    </div>
  );
}
