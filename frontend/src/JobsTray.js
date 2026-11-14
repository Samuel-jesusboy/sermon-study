import React, { useState } from 'react';
import toast from 'react-hot-toast';
import { api } from './api';
import { useApp } from './AppContext';

function label(j) {
  if (j.filename) return j.filename;
  if (j.video_id) return `YouTube ${j.video_id}`;
  return j.source === 'paste' ? 'Pasted transcript' : 'Sermon';
}

// Live progress for sermons being processed in the background.
export default function JobsTray() {
  const { jobs, loadJobs, openSermon } = useApp();
  const [open, setOpen] = useState(null); // null = follow activity: open while something is processing
  const visible = jobs.filter(j => j.status !== 'done' || Date.now() - new Date(j.updated_at).getTime() < 10 * 60 * 1000).slice(0, 8);
  const active = visible.filter(j => j.status === 'queued' || j.status === 'running');
  if (!visible.length) return null;
  const isOpen = open === null ? active.length > 0 : open;

  const retry = async (id) => {
    try { await api.retryJob(id); loadJobs(); toast('Trying again…'); } catch (e) { toast.error(e.message); }
  };
  const dismiss = async (id) => { try { await api.dismissJob(id); loadJobs(); } catch (e) { /* ignore */ } };

  return (
    <div className={`jobs-tray ${isOpen ? '' : 'collapsed'}`}>
      <button className="jobs-tray-head" onClick={() => setOpen(!isOpen)}>
        {active.length ? <><span className="spinner small" /> Processing {active.length} sermon{active.length > 1 ? 's' : ''}</> : 'Recent processing'}
        {!active.length && visible.some(j => j.status === 'failed') && <span className="tray-badge">{visible.filter(j => j.status === 'failed').length} failed</span>}
        <span style={{ marginLeft: 'auto' }}>{isOpen ? '▾' : '▴'}</span>
      </button>
      {isOpen && visible.map(j => (
        <div className="job-row" key={j.id}>
          <div className="job-top">
            <span className="job-name">{label(j)}</span>
            {j.status === 'done' && <button className="link-btn" onClick={() => openSermon(j.sermon_id)}>Open</button>}
            {j.status === 'failed' && j.source !== 'upload' && <button className="link-btn" onClick={() => retry(j.id)}>Retry</button>}
            {j.status !== 'running' && <button className="link-btn quiet" onClick={() => dismiss(j.id)} aria-label="Dismiss">✕</button>}
          </div>
          {j.status === 'failed'
            ? <p className="job-error">{j.error}</p>
            : <>
                <div className="progress"><div style={{ width: `${j.status === 'done' ? 100 : j.progress}%` }} /></div>
                <p className="job-step">{j.status === 'done' ? 'Notes ready' : j.step}</p>
              </>}
        </div>
      ))}
    </div>
  );
}
