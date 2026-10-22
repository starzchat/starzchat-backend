import { useState } from 'react';
import { toast } from 'sonner';
import { useStore } from '../store.js';

const input = 'w-full rounded-lg bg-[#202c33] px-3 py-2 outline-none focus:ring-2 focus:ring-[#00a884]';

export default function AuthScreen() {
  const authenticate = useStore((s) => s.authenticate);
  const [mode, setMode] = useState('login');
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ student_id: '', username: '', display_name: '', password: '' });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === 'login') await authenticate('login', { username: f.username.trim(), password: f.password });
      else {
        const body = { student_id: f.student_id.trim().toUpperCase(), username: f.username.trim(), password: f.password };
        if (f.display_name.trim()) body.display_name = f.display_name.trim();
        await authenticate('register', body);
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid h-full place-items-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-3 rounded-2xl bg-[#111b21] p-6">
        <h1 className="text-2xl font-semibold text-[#00a884]">StarzChat</h1>
        <div className="flex gap-2 text-sm" role="tablist">
          {['login', 'register'].map((m) => (
            <button type="button" key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
              className={`flex-1 rounded-lg py-1.5 capitalize ${mode === m ? 'bg-[#00a884] text-black' : 'bg-[#202c33]'}`}>
              {m}
            </button>
          ))}
        </div>
        {mode === 'register' && (
          <>
            <input className={input} placeholder="Student ID" value={f.student_id} onChange={set('student_id')} required />
            <input className={input} placeholder="Display name (optional)" value={f.display_name} onChange={set('display_name')} />
          </>
        )}
        <input className={input} placeholder="Username" autoComplete="username" value={f.username} onChange={set('username')} required />
        <input className={input} type="password" placeholder="Password (min 8)" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={mode === 'register' ? 8 : undefined} value={f.password} onChange={set('password')} required />
        <button disabled={busy} className="w-full rounded-lg bg-[#00a884] py-2 font-medium text-black disabled:opacity-50">
          {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
        </button>
      </form>
    </div>
  );
}
