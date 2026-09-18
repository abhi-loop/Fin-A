import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    try {
      await register(form.name, form.email, form.password);
      navigate('/dashboard');
    } catch {
      setError('Could not register. That email may already be in use.');
    }
  };

  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="card w-full max-w-sm">
        <p className="text-lg font-bold">Create account</p>
        <p className="mb-5 mt-1 text-sm text-slate-500">Start tracking in a minute.</p>
        <div className="space-y-3">
          <input className="input" placeholder="Full name" value={form.name} onChange={set('name')} />
          <input className="input" type="email" placeholder="Email" value={form.email} onChange={set('email')} />
          <input className="input" type="password" placeholder="Password" value={form.password} onChange={set('password')} />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button className="btn w-full" onClick={submit}>Create account</button>
          <p className="text-center text-xs text-slate-500">
            Have an account? <Link to="/login" className="text-brand">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
