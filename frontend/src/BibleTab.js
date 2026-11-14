import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import toast from 'react-hot-toast';

export default function BibleTab() {
  const [version, setVersion] = useState('kjv');
  const [books, setBooks] = useState([]);
  const [selectedBook, setSelectedBook] = useState('');
  const [selectedChapter, setSelectedChapter] = useState(1);
  const [chapterData, setChapterData] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [lookupRef, setLookupRef] = useState('');
  const [lookupResult, setLookupResult] = useState(null);
  const [tab, setTab] = useState('read');
  const [loading, setLoading] = useState(false);

  const loadBooks = useCallback(async () => {
    try {
      const data = await api.getBibleBooks(version);
      setBooks(data);
      if (data.length && !selectedBook) setSelectedBook(data[0].name);
    } catch (e) { toast.error('Could not load Bible: ' + e.message); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const loadChapter = useCallback(async () => {
    if (!selectedBook) return;
    setLoading(true);
    try {
      const data = await api.getChapter(selectedBook, selectedChapter, version);
      setChapterData(data);
    } catch (e) { toast.error(e.message); }
    setLoading(false);
  }, [selectedBook, selectedChapter, version]);

  useEffect(() => { loadBooks(); }, [loadBooks]);
  useEffect(() => { if (selectedBook) loadChapter(); }, [selectedBook, loadChapter]);

  const search = async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    try {
      const data = await api.searchBible(searchQuery, version);
      setSearchResults(data.results);
    } catch (e) { toast.error(e.message); }
    setLoading(false);
  };

  const lookup = async () => {
    if (!lookupRef.trim()) return;
    setLoading(true);
    try {
      const data = await api.lookupVerse(lookupRef, version);
      setLookupResult(data);
    } catch (e) { toast.error('Could not find: ' + lookupRef); }
    setLoading(false);
  };

  const currentBook = books.find(b => b.name === selectedBook);

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Bible</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>Version:</span>
          <div style={{ display: 'flex', gap: 4, background: 'var(--cream-dark)', borderRadius: 20, padding: 3 }}>
            {['kjv', 'web', 'webbe', 'bbe', 'oeb-us'].map(v => (
              <button key={v} onClick={() => setVersion(v)} style={{ padding: '4px 12px', borderRadius: 16, border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, sans-serif', background: version === v ? 'var(--purple)' : 'transparent', color: version === v ? 'white' : 'var(--text-soft)', transition: 'all 0.15s' }}>
                {v.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="tabs-row">
        {['read', 'search', 'lookup'].map(t => (
          <button key={t} className={`tab-btn ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t === 'read' ? '📖 Read' : t === 'search' ? '🔍 Search' : '🔢 Lookup'}
          </button>
        ))}
      </div>

      {tab === 'read' && (
        <div className="card">
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <select value={selectedBook} onChange={e => { setSelectedBook(e.target.value); setSelectedChapter(1); }} style={{ flex: 2 }}>
              {books.map(b => <option key={b.name} value={b.name}>{b.name}</option>)}
            </select>
            <select value={selectedChapter} onChange={e => setSelectedChapter(Number(e.target.value))} style={{ flex: 1 }}>
              {Array.from({ length: currentBook?.chapters || 1 }).map((_, i) => (
                <option key={i + 1} value={i + 1}>Chapter {i + 1}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="loading"><div className="spinner" /> Loading...</div>
          ) : chapterData ? (
            <>
              <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-soft)', marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                {chapterData.book} {chapterData.chapter} · {version.toUpperCase()}
              </p>
              {chapterData.verses.map(v => (
                <div className="bible-verse" key={v.verse}>
                  <span className="verse-num">{v.verse}</span>
                  <span className="verse-text">{v.text}</span>
                </div>
              ))}
              <div className="btn-row" style={{ marginTop: 16, justifyContent: 'space-between' }}>
                <button className="btn btn-sm" onClick={() => setSelectedChapter(c => Math.max(1, c - 1))} disabled={selectedChapter <= 1}>← Prev</button>
                <button className="btn btn-sm" onClick={() => setSelectedChapter(c => Math.min(currentBook?.chapters || 1, c + 1))} disabled={selectedChapter >= (currentBook?.chapters || 1)}>Next →</button>
              </div>
            </>
          ) : null}
        </div>
      )}

      {tab === 'search' && (
        <div className="card">
          <p className="card-title">Search the Bible</p>
          <p style={{ fontSize: 12, color: 'var(--text-soft)', marginBottom: 10 }}>Enter a reference like "John 3:16" or a passage like "Romans 8:28-30"</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder='e.g. John 3:16 or Psalms 23' onKeyDown={e => e.key === 'Enter' && search()} style={{ flex: 1 }} />
            <button className="btn btn-primary" onClick={search} disabled={loading}>Search</button>
          </div>
          {loading && <div className="loading"><div className="spinner" /> Searching...</div>}
          {searchResults.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text-soft)', marginBottom: 10 }}>{searchResults.length} results</p>
              {searchResults.map((r, i) => (
                <div key={i} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                  <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--gold-deep)', marginBottom: 4 }}>{r.reference}</p>
                  <p style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.7 }}>{r.text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'lookup' && (
        <div className="card">
          <p className="card-title">Look up a reference</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input type="text" value={lookupRef} onChange={e => setLookupRef(e.target.value)} placeholder='e.g. John 3:16 or Romans 8:28-30' onKeyDown={e => e.key === 'Enter' && lookup()} style={{ flex: 1 }} />
            <button className="btn btn-primary" onClick={lookup} disabled={loading}>Look up</button>
          </div>
          {loading && <div className="loading"><div className="spinner" /> Looking up...</div>}
          {lookupResult && (
            <div style={{ marginTop: 16, background: 'var(--gold-light)', borderRadius: 'var(--radius-sm)', padding: '1rem' }}>
              <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--gold-deep)', marginBottom: 10 }}>{lookupResult.reference} · {lookupResult.version}</p>
              {lookupResult.verses.map(v => (
                <div key={v.verse} style={{ marginBottom: 8 }}>
                  <span className="verse-num">{v.verse}</span>
                  <span style={{ fontSize: 15, color: 'var(--gold-deep)', lineHeight: 1.8, fontFamily: 'Lora, serif', fontStyle: 'italic' }}>{v.text}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
