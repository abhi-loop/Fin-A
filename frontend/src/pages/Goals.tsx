import { ErrorState, PageHeader, ProgressBar, Skeleton } from '../components/common';
import { useFetch } from '../hooks';
import { formatINR, goalsApi } from '../services/api';

export default function Goals() {
  const { data, loading, error, reload } = useFetch(goalsApi.list);
  if (loading) return <Skeleton rows={3} />;
  if (error || !data) return <ErrorState message={error ?? 'No data'} onRetry={reload} />;

  return (
    <>
      <PageHeader title="Goals" subtitle="Track progress toward your savings goals." />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.map((g) => (
          <div key={g.name} className="card">
            <p className="font-semibold">{g.name}</p>
            <p className="mb-3 text-xs text-slate-500">Deadline {g.deadline}</p>
            <p className="text-2xl font-bold tracking-tight">
              {formatINR(g.saved)}
              <span className="ml-1 text-sm font-medium text-slate-500">
                of {formatINR(g.target)}
              </span>
            </p>
            <ProgressBar pct={g.progress_pct} />
            <div className="mt-2 flex justify-between text-xs text-slate-500">
              <span>{g.progress_pct}% complete</span>
              <span>{formatINR(g.remaining)} to go</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
