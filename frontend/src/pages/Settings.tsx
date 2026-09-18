import { PageHeader, Section } from '../components/common';
import { useAuth } from '../context/AuthContext';

export default function Settings() {
  const { user, logout } = useAuth();
  return (
    <>
      <PageHeader title="Settings" subtitle="Account and preferences." />
      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Profile">
          {[['Name', user?.name], ['Email', user?.email], ['Currency', 'INR (₹)']]
            .map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-slate-100 py-2.5 text-sm last:border-0 dark:border-slate-800">
                <span className="text-slate-500">{k}</span>
                <span>{v}</span>
              </div>
            ))}
        </Section>
        <Section title="Session">
          <p className="mb-3 text-sm text-slate-500">Sign out of this device.</p>
          <button className="btn-ghost" onClick={logout}>Log out</button>
        </Section>
      </div>
    </>
  );
}
