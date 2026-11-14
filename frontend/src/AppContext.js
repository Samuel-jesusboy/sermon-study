import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { api } from './api';
import { supabase } from './supabase';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

export function AppProvider({ children }) {
  const [session, setSession] = useState(null);
  const [authReady, setAuthReady] = useState(!supabase);
  const [config, setConfig] = useState({ models: [], default_model: null });
  const [jobs, setJobs] = useState([]);
  const [model, setModelState] = useState(() => localStorage.getItem('ss_model') || '');
  const [library, setLibraryVersion] = useState(0); // bump to make lists reload
  const [openRequest, setOpenRequest] = useState(null); // { sermonId, seconds }
  const seen = useRef(new Set());

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setAuthReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    api.config().then(cfg => {
      setConfig(cfg);
      setModelState(m => (cfg.models.some(x => x.id === m) ? m : cfg.default_model || ''));
    }).catch(() => {});
  }, []);

  const setModel = (m) => { setModelState(m); try { localStorage.setItem('ss_model', m); } catch (e) { /* private mode */ } };
  const refreshLibrary = useCallback(() => setLibraryVersion(v => v + 1), []);
  const openSermon = useCallback((sermonId, seconds = null) => setOpenRequest({ sermonId, seconds, at: Date.now() }), []);

  const loadJobs = useCallback(async () => {
    if (!session) return;
    try {
      const list = await api.listJobs();
      setJobs(list);
      list.forEach(j => {
        if (seen.current.has(j.id + j.status)) return;
        const wasActive = seen.current.has(j.id + 'running') || seen.current.has(j.id + 'queued');
        seen.current.add(j.id + j.status);
        if (!wasActive) return;
        if (j.status === 'done') {
          refreshLibrary();
          toast.success(t => (
            <span>Sermon notes are ready. <button className="link-btn" onClick={() => { openSermon(j.sermon_id); toast.dismiss(t.id); }}>Open</button></span>
          ), { duration: 8000 });
        } else if (j.status === 'failed') {
          toast.error(j.error || 'A sermon could not be processed', { duration: 8000 });
        }
      });
    } catch (e) { /* the tray shows nothing if the server is down */ }
  }, [session, refreshLibrary, openSermon]);

  const active = jobs.some(j => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!session) return;
    loadJobs();
    const id = setInterval(loadJobs, active ? 3000 : 30000);
    return () => clearInterval(id);
  }, [session, active, loadJobs]);

  // Check churches with auto-import on, once per app open
  useEffect(() => {
    if (!session) return;
    api.syncChurches().then(r => {
      if (r.queued > 0) { toast(`Found ${r.queued} new sermon${r.queued > 1 ? 's' : ''} from your churches`); loadJobs(); }
    }).catch(() => {});
  }, [session, loadJobs]);

  const trackJob = (job) => {
    if (!job) return;
    seen.current.add(job.id + 'queued');
    setJobs(js => [job, ...js.filter(j => j.id !== job.id)]);
  };

  return (
    <Ctx.Provider value={{ session, authReady, config, model, setModel, jobs, loadJobs, trackJob,
      library, refreshLibrary, openRequest, openSermon, clearOpenRequest: () => setOpenRequest(null) }}>
      {children}
    </Ctx.Provider>
  );
}
