import { ErrorState, PageHeader, Skeleton } from '../components/common';
import { useFetch } from '../hooks';
import { alertsApi } from '../services/api';

const DOT: Record<string, string> = {
  high: 'bg-red-500', med: 'bg-amber-500', low: 'bg-emerald-500',
};

export default function Alerts() {
  const { data, loading, error, reload } = useFetch(alertsApi.list);
  if (loading) return <Skeleton rows={4} />;
  if (error || !data) return <ErrorState message={error ?? 'No data'} onRetry={reload} />;

  const unread = data.filter((a) => !a.read).length;
  const markRead = async (id: number) => { await alertsApi.markRead(id); reload(); };

  return (
    <>
      <PageHeader title="Alerts"
        subtitle={`${unread} unread notification${unread === 1 ? '' : 's'}.`} />
      <div className="card">
        {data.map((a) => (
          <div key={a.id}
            className={`flex gap-3 border-b border-slate-100 py-3 last:border-0 dark:border-slate-800 ${a.read ? 'opacity-60' : ''}`}>
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT[a.severity]}`} />
            <div className="flex-1">
              <p className="text-sm font-semibold">
                {a.title} <span className="chip ml-1">{a.category}</span>
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">{a.message}</p>
              <p className="mt-1 text-xs text-slate-400">
                {new Date(a.createdAt).toLocaleString('en-IN')}
              </p>
            </div>
            {!a.read && (
              <button className="btn-ghost h-fit text-xs" onClick={() => markRead(a.id)}>
                Mark read
              </button>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
