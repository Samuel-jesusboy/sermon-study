import React, { useEffect, useState } from 'react';
import { Toaster } from 'react-hot-toast';
import { AppProvider, useApp } from './AppContext';
import AuthScreen from './AuthScreen';
import JobsTray from './JobsTray';
import PublicSermon from './PublicSermon';
import SermonsTab from './SermonsTab';
import BibleTab from './BibleTab';
import AskTab from './AskTab';
import ChurchesTab from './ChurchesTab';
import StudyGuideTab from './StudyGuideTab';
import UsageTab from './UsageTab';
import { supabase } from './supabase';
import './styles.css';

const NAV = [
  { id: 'sermons', label: 'Sermons', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" /></svg> },
  { id: 'bible', label: 'Bible', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg> },
  { id: 'ask', label: 'Ask', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg> },
  { id: 'churches', label: 'Churches', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v4M10 4h4M5 21V11l7-5 7 5v10" /><path d="M9 21v-5h6v5" /></svg> },
  { id: 'guide', label: 'Study Guide', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></svg> },
];

function Shell() {
  const { session, authReady, openRequest } = useApp();
  const [tab, setTab] = useState('sermons');

  // Opening a sermon from Ask or a job notification switches to the Sermons tab
  useEffect(() => { if (openRequest) setTab('sermons'); }, [openRequest]);

  if (!authReady) return <div className="loading" style={{ marginTop: '30vh' }}><div className="spinner" /></div>;
  if (!session) return <AuthScreen />;

  return (
    <div className="app-shell">
      <header className="topbar no-print">
        <div className="topbar-logo"><span>✝︎</span> Sermon Study</div>
        <div className="topbar-right">
          <button className={`btn btn-ghost btn-sm ${tab === 'usage' ? 'active-link' : ''}`} onClick={() => setTab('usage')}>Usage</button>
          <span className="soft hide-mobile">{session.user?.email}</span>
          <button className="btn btn-ghost btn-sm" onClick={() => supabase.auth.signOut()}>Sign out</button>
        </div>
      </header>
      <main className="main-content">
        <JobsTray />
        {tab === 'sermons' && <SermonsTab />}
        {tab === 'bible' && <BibleTab />}
        {tab === 'ask' && <AskTab />}
        {tab === 'churches' && <ChurchesTab />}
        {tab === 'guide' && <StudyGuideTab />}
        {tab === 'usage' && <UsageTab />}
      </main>
      <nav className="bottom-nav no-print">
        {NAV.map(n => (
          <button key={n.id} className={`nav-item ${tab === n.id ? 'active' : ''}`} onClick={() => setTab(n.id)}>{n.icon}{n.label}</button>
        ))}
      </nav>
    </div>
  );
}

export default function App() {
  const shared = window.location.pathname.match(/^\/s\/([0-9a-f-]{36})\/?$/i);
  return (
    <>
      <Toaster position="top-center" toastOptions={{ duration: 4000, style: { fontFamily: 'Inter, sans-serif', fontSize: 14 } }} />
      {shared ? <PublicSermon id={shared[1]} /> : <AppProvider><Shell /></AppProvider>}
    </>
  );
}
