import React, { useEffect, useState } from 'react';
import { api } from './api';
import SermonDetail from './SermonDetail';

// The page behind a share link: read-only, no sign-in needed.
export default function PublicSermon({ id }) {
  const [sermon, setSermon] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.publicSermon(id).then(s => { setSermon(s); document.title = `${s.title} · Sermon Study`; })
      .catch(e => setError(e.message));
  }, [id]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a href="/" className="topbar-logo" style={{ textDecoration: 'none' }}><span>✝︎</span> Sermon Study</a>
        <a href="/" className="btn btn-sm btn-primary no-print">Make your own notes</a>
      </header>
      <main className="main-content" style={{ paddingBottom: '2rem' }}>
        {error && <div className="empty-state"><div className="icon">🔒</div><p>{error}</p></div>}
        {!error && !sermon && <div className="loading"><div className="spinner" /> Loading notes…</div>}
        {sermon && <SermonDetail sermon={sermon} readOnly />}
      </main>
    </div>
  );
}
