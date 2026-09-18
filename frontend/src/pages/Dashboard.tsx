import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis,
} from 'recharts';
import {
  EmptyState, ErrorState, KpiCard, PageHeader, ProgressBar, Section, Skeleton,
} from '../components/common';
import { useFetch } from '../hooks';
import { dashboardApi, formatINR } from '../services/api';

export default function Dashboard() {
  const { data, loading, error, reload } = useFetch(dashboardApi.get);

  if (loading) return <Skeleton rows={5} />;
  if (error || !data) return <ErrorState message={error ?? 'No data'} onRetry={reload} />;

  // Calculate the last 6 months dynamically
  const today = new Date();
  const MONTHS = Array.from({ length: 6 }).map((_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth() - (5 - i), 1);
    return d.toLocaleString('default', { month: 'short' });
  });

  const chart = data.trend.map((v, i) => ({ month: MONTHS[i] ?? '', spend: v }));
  const totalSpend = Object.values(data.spendingByCategory).reduce((a, b) => a + b, 0);

  return (
    <>
      <PageHeader
        title={`Good morning, ${data.user.name} 👋`}
        subtitle="Here is your financial overview for this month."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Total Balance" value={formatINR(data.balance)} hint="Across all accounts" />
        <KpiCard label="Monthly Income" value={formatINR(data.income)} hint="Salary credited" />
        <KpiCard label="Monthly Expenses" value={formatINR(data.expenses)} hint="This month" />
        <KpiCard label="Savings" value={formatINR(data.savings)}
          hint={`${data.savingsRatePct}% of income`} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Section title="Spending Overview">
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="month" tickLine={false} axisLine={false} fontSize={12} />
              <Tooltip formatter={(v: number) => formatINR(v)} />
              <Area type="monotone" dataKey="spend" stroke="#1f6feb"
                fill="#1f6feb" fillOpacity={0.12} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Expense Categories">
          {Object.entries(data.spendingByCategory).slice(0, 6).map(([cat, val]) => (
            <div key={cat} className="mb-3">
              <div className="flex justify-between text-sm">
                <span>{cat}</span>
                <span className="text-slate-500">{formatINR(val)}</span>
              </div>
              <ProgressBar pct={(val / totalSpend) * 100} />
            </div>
          ))}
        </Section>

        <Section title="Budget Progress">
          {data.budget.slice(0, 4).map((b) => (
            <div key={b.category} className="mb-3">
              <div className="flex justify-between text-sm">
                <span>{b.category}</span>
                <span className="text-slate-500">{b.used_pct}%</span>
              </div>
              <ProgressBar pct={b.used_pct} />
            </div>
          ))}
        </Section>

        <Section title="Recent Transactions">
          {data.recentTransactions.length === 0
            ? <EmptyState message="No transactions yet." />
            : data.recentTransactions.map((t, i) => (
              <div key={i} className="flex justify-between border-b border-slate-100 py-2.5 last:border-0 dark:border-slate-800">
                <div>
                  <p className="text-sm">{t.description}</p>
                  <p className="text-xs text-slate-500">{t.date} · {t.category}</p>
                </div>
                <span className={`text-sm font-semibold ${t.amount > 0 ? 'text-emerald-600' : ''}`}>
                  {t.amount > 0 ? '+' : '−'}{formatINR(t.amount)}
                </span>
              </div>
            ))}
        </Section>

        <Section title="Financial Insights">
          {data.alerts.map((a) => (
            <div key={a.title} className="flex gap-3 border-b border-slate-100 py-2.5 last:border-0 dark:border-slate-800">
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                a.severity === 'high' ? 'bg-red-500'
                  : a.severity === 'med' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
              <div>
                <p className="text-sm font-semibold">{a.title}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{a.message}</p>
              </div>
            </div>
          ))}
        </Section>

        <Section title="Savings Goals">
          {data.goals.map((g) => (
            <div key={g.name} className="mb-3">
              <div className="flex justify-between text-sm">
                <span>{g.name}</span>
                <span className="text-slate-500">
                  {formatINR(g.saved)} / {formatINR(g.target)}
                </span>
              </div>
              <ProgressBar pct={g.progress_pct} />
            </div>
          ))}
        </Section>
      </div>
    </>
  );
}
