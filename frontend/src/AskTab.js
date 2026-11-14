import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import toast from 'react-hot-toast';
import { api } from './api';
import { useApp } from './AppContext';
import ModelSelector from './ModelSelector';

const SUGGESTIONS = [
  'What has my pastor taught about faith in hard times?',
  'What do my sermons say about prayer?',
  'How do I hear from God in daily life?',
  'What is grace and how do I receive it?',
  'What did the sermons teach about marriage and relationships?',
  'How should a Christian handle fear and anxiety?',
];

function Sources({ sources }) {
  const { openSermon } = useApp();
  if (!sources?.length) return null;
  return (
    <div className="sources">
      <p className="mini-label">From your sermons</p>
      {sources.map(s => (
        <div key={s.n} className="source">
          <span className="source-n">{s.n}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p className="source-title">{s.title}</p>
            <p className="soft">{[s.preacher, s.church_name].filter(Boolean).join(' · ')} · at {s.time}</p>
            <p className="source-excerpt">“{s.excerpt.slice(0, 220)}{s.excerpt.length > 220 ? '…' : ''}”</p>
          </div>
          <button className="btn btn-sm" onClick={() => openSermon(s.sermon_id, s.start_seconds)}>Open at {s.time}</button>
        </div>
      ))}
    </div>
  );
}

export default function AskTab() {
  const { model } = useApp();
  const [tab, setTab] = useState('ask');
  const [question, setQuestion] = useState('');
  const [verseQuery, setVerseQuery] = useState('');
  const [answer, setAnswer] = useState(null);
  const [verseAnswer, setVerseAnswer] = useState(null);
  const [loading, setLoading] = useState(false);

  const ask = async () => {
    if (!question.trim()) return toast.error('Type a question first');
    setLoading(true); setAnswer(null);
    try { setAnswer(await api.ask({ question, model: model || undefined })); } catch (e) { toast.error(e.message); }
    setLoading(false);
  };

  const explain = async () => {
    if (!verseQuery.trim()) return toast.error('Enter a verse or passage');
    setLoading(true); setVerseAnswer(null);
    try { setVerseAnswer(await api.explainVerse({ question: verseQuery, model: model || undefined })); } catch (e) { toast.error(e.message); }
    setLoading(false);
  };

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Ask</h2>
        <ModelSelector />
      </div>
      <div className="tabs-row">
        <button className={`tab-btn ${tab === 'ask' ? 'active' : ''}`} onClick={() => setTab('ask')}>Ask your library</button>
        <button className={`tab-btn ${tab === 'verse' ? 'active' : ''}`} onClick={() => setTab('verse')}>Explain a verse</button>
      </div>

      {tab === 'ask' && (
        <>
          <div className="card">
            <p className="card-title">Ask from your sermons</p>
            <p className="hint" style={{ marginTop: 0, marginBottom: 12 }}>Answers quote your sermons and link to the exact minute, so you can check what was actually said.</p>
            <textarea value={question} onChange={e => setQuestion(e.target.value)} style={{ minHeight: 80 }}
              placeholder="e.g. What does Pastor Sam teach about purpose?"
              onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask(); }} />
            <div className="btn-row">
              <button className="btn btn-primary" onClick={ask} disabled={loading || !question.trim()}>
                {loading ? <><span className="spinner small light" /> Searching your sermons…</> : 'Ask'}
              </button>
            </div>
          </div>
          {!answer && (
            <div className="chip-row" style={{ marginBottom: 16 }}>
              {SUGGESTIONS.map(s => <button key={s} className="chip" onClick={() => setQuestion(s)}>{s}</button>)}
            </div>
          )}
          {answer && (
            <div className="answer-box">
              <div className="sermon-meta" style={{ marginBottom: 10 }}>
                <span className="mini-label" style={{ color: 'var(--purple)', margin: 0 }}>Answer</span>
                {answer.library_matches > 0 ? <span className="badge badge-gold">From {answer.sources.length} sermon passage{answer.sources.length > 1 ? 's' : ''}</span>
                  : <span className="badge">No matching sermons yet</span>}
              </div>
              <div className="markdown"><ReactMarkdown>{answer.answer}</ReactMarkdown></div>
              <Sources sources={answer.sources} />
            </div>
          )}
        </>
      )}

      {tab === 'verse' && (
        <>
          <div className="card">
            <p className="card-title">Explain a Bible verse or passage</p>
            <textarea value={verseQuery} onChange={e => setVerseQuery(e.target.value)} style={{ minHeight: 70 }}
              placeholder='e.g. John 3:16, Romans 8:28-30 or Proverbs 3:5-6' />
            <div className="btn-row">
              <button className="btn btn-primary" onClick={explain} disabled={loading || !verseQuery.trim()}>
                {loading ? <><span className="spinner small light" /> Explaining…</> : 'Explain'}
              </button>
            </div>
          </div>
          {verseAnswer && (
            <div className="answer-box">
              <p className="ref">{verseAnswer.reference}</p>
              {verseAnswer.verse_text && <p className="verse-quote">{verseAnswer.verse_text}</p>}
              <div className="markdown"><ReactMarkdown>{verseAnswer.explanation}</ReactMarkdown></div>
              <Sources sources={verseAnswer.sources} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
