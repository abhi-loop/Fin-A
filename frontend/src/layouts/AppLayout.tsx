import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  AlertTriangle, LayoutDashboard, LineChart, LogOut, Menu, Moon, Receipt,
  Settings as Cog, Sparkles, Sun, Target, Wallet,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/assistant', label: 'AI Assistant', Icon: Sparkles },
  { to: '/transactions', label: 'Transactions', Icon: Receipt },
  { to: '/budget', label: 'Budget', Icon: Wallet },
  { to: '/goals', label: 'Goals', Icon: Target },
  { to: '/investments', label: 'Investments', Icon: LineChart },
  { to: '/alerts', label: 'Alerts', Icon: AlertTriangle },
  { to: '/settings', label: 'Settings', Icon: Cog },
];

export default function AppLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains('dark'),
  );

  const toggleTheme = () => {
    document.documentElement.classList.toggle('dark');
    setDark((d) => !d);
  };

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <header className="flex items-center justify-between border-b border-slate-200 p-4 md:hidden dark:border-slate-800">
        <span className="text-lg font-bold">Fin<span className="text-brand">Agent</span></span>
        <button onClick={() => setOpen((o) => !o)} aria-label="Menu">
          <Menu size={20} />
        </button>
      </header>

      <aside
        className={`${open ? 'block' : 'hidden'} w-full shrink-0 border-b border-slate-200 bg-white p-3 md:block md:w-60 md:border-b-0 md:border-r md:p-4 dark:border-slate-800 dark:bg-[#141922]`}
      >
        <div className="hidden px-2 pb-5 pt-1 text-lg font-bold tracking-tight md:block">
          Fin<span className="text-brand">Agent</span>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand text-white'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                }`}
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-6 flex gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
          <button className="btn-ghost flex-1" onClick={toggleTheme}>
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <button
            className="btn-ghost flex-1"
            onClick={() => { logout(); navigate('/login'); }}
          >
            <LogOut size={15} />
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-x-hidden p-5 md:p-8">
        <Outlet />
      </main>
    </div>
  );
}
