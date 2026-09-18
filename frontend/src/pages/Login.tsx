import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch {
      setError('Invalid credentials, or the backend is not running.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="card w-full max-w-sm">
        <p className="text-lg font-bold">Fin<span className="text-brand">Agent</span></p>
        <p className="mb-5 mt-1 text-sm text-slate-500">Sign in to your workspace.</p>
        <div className="space-y-3">
          <input className="input" type="email" placeholder="Email"
            value={email} onChange={(e) => setEmail(e.target.value)} />
          <input className="input" type="password" placeholder="Password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()} />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button className="btn w-full" onClick={submit} disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="text-center text-xs text-slate-500">
            No account? <Link to="/register" className="text-brand">Register</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
