import {
  ErrorState, KpiCard, PageHeader, ProgressBar, Section, Skeleton,
} from '../components/common';
import { useFetch } from '../hooks';
import { budgetApi, formatINR } from '../services/api';

export default function Budget() {
  const { data, loading, error, reload } = useFetch(budgetApi.get);
  if (loading) return <Skeleton rows={4} />;
  if (error || !data) return <ErrorState message={error ?? 'No data'} onRetry={reload} />;

  const spent = data.budget.reduce((a, b) => a + b.spent, 0);

  return (
    <>
      <PageHeader title="Budget" subtitle="Monthly category limits and usage." />
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard label="Total Budget" value={formatINR(data.total_budget)}
          hint={`${data.budget.length} categories`} />
        <KpiCard label="Spent" value={formatINR(spent)}
          hint={`${Math.round((spent / data.total_budget) * 100)}% used`} />
        <KpiCard label="Remaining" value={formatINR(data.total_budget - spent)} />
      </div>
      <div className="mt-4">
        <Section title="Category Budgets">
          {data.budget.map((b) => (
            <div key={b.category} className="mb-4">
              <div className="flex justify-between text-sm">
                <span className="font-semibold">
                  {b.category}
                  {b.used_pct > 90 && (
                    <span className="ml-2 rounded-full bg-red-50 px-2 py-0.5 text-[11px] text-red-600 dark:bg-red-950">
                      near limit
                    </span>
                  )}
                </span>
                <span className="text-slate-500">
                  {formatINR(b.spent)} / {formatINR(b.limit)}
                </span>
              </div>
              <ProgressBar pct={b.used_pct} />
            </div>
          ))}
        </Section>
      </div>
    </>
  );
}
