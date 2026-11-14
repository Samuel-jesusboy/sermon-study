import React, { useState } from 'react';
import toast from 'react-hot-toast';
import { supabase, supabaseConfigured } from './supabase';

export default function AuthScreen() {
  const [mode, setMode] = useState('signin'); // signin | signup | reset
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState('');

  if (!supabaseConfigured) {
    return (
      <div className="auth-wrap"><div className="card auth-card">
        <h1 className="auth-title">✝︎ Sermon Study</h1>
        <p className="auth-note">The app isn't configured yet. Set <code>REACT_APP_SUPABASE_URL</code> and{' '}
          <code>REACT_APP_SUPABASE_KEY</code> in <code>frontend/.env</code>, then restart.</p>
      </div></div>
    );
  }

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === 'signin') {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      } else if (mode === 'signup') {
        const { data, error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin } });
        if (error) throw error;
        if (!data.session) setSent('Check your email to confirm your account, then sign in.');
      } else {
        const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
        if (error) throw error;
        setSent('If that email has an account, a reset link is on its way.');
      }
    } catch (err) {
      toast.error(err.message || 'Something went wrong');
    }
    setBusy(false);
  };

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <h1 className="auth-title">✝︎ Sermon Study</h1>
        <p className="auth-note">Turn every sermon into full notes, verses and study questions you can search and share.</p>
        {sent ? <p className="notice">{sent}</p> : (
          <>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input type="email" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" />
            </div>
            {mode !== 'reset' && (
              <div className="form-group">
                <label className="form-label">Password</label>
                <input type="password" required minLength={6} value={password} onChange={e => setPassword(e.target.value)}
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} />
              </div>
            )}
            <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={busy}>
              {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : mode === 'signup' ? 'Create account' : 'Send reset link'}
            </button>
          </>
        )}
        <div className="auth-links">
          {mode !== 'signin' && <button type="button" className="link-btn" onClick={() => { setMode('signin'); setSent(''); }}>Sign in</button>}
          {mode !== 'signup' && <button type="button" className="link-btn" onClick={() => { setMode('signup'); setSent(''); }}>Create an account</button>}
          {mode !== 'reset' && <button type="button" className="link-btn" onClick={() => { setMode('reset'); setSent(''); }}>Forgot password?</button>}
        </div>
      </form>
    </div>
  );
}
