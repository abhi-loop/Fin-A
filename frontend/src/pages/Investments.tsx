import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import {
  ErrorState, KpiCard, PageHeader, Section, Skeleton,
} from '../components/common';
import { useFetch } from '../hooks';
import { formatINR, investmentsApi } from '../services/api';

const COLORS = ['#1f6feb', '#0f9d58', '#e8a33d', '#8b5cf6'];

export default function Investments() {
  const { data, loading, error, reload } = useFetch(investmentsApi.get);
  if (loading) return <Skeleton rows={4} />;
  if (error || !data) return <ErrorState message={error ?? 'No data'} onRetry={reload} />;

  const pie = data.holdings.map((h) => ({ name: h.asset, value: h.current }));

  return (
    <>
      <PageHeader title="Investments"
        subtitle="Portfolio snapshot. Past performance does not indicate future returns." />
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard label="Portfolio Value" value={formatINR(data.total_current)}
          hint={`${data.holdings.length} holdings`} />
        <KpiCard label="Invested" value={formatINR(data.total_invested)} hint="Total cost" />
        <KpiCard label="Unrealised Gain" value={formatINR(data.unrealised_gain)}
          hint={`${((data.unrealised_gain / data.total_invested) * 100).toFixed(1)}%`} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Section title="Allocation">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85}>
                {pie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v: number) => formatINR(v)} />
            </PieChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Holdings">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="label">
                  <th className="py-2 text-left">Asset</th>
                  <th className="py-2 text-right">Invested</th>
                  <th className="py-2 text-right">Current</th>
                  <th className="py-2 text-right">Return</th>
                </tr>
              </thead>
              <tbody>
                {data.holdings.map((h) => (
                  <tr key={h.asset} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-3">{h.asset}</td>
                    <td className="py-3 text-right">{formatINR(h.invested)}</td>
                    <td className="py-3 text-right">{formatINR(h.current)}</td>
                    <td className="py-3 text-right font-semibold text-emerald-600">
                      +{(((h.current - h.invested) / h.invested) * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </>
  );
}
