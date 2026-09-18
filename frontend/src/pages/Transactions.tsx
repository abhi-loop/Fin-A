import { useMemo, useState } from 'react';
import { Trash2 } from 'lucide-react';
import {
  EmptyState, ErrorState, PageHeader, Skeleton,
} from '../components/common';
import { useFetch } from '../hooks';
import { formatINR, transactionsApi } from '../services/api';

const CATEGORIES = ['All', 'Food', 'Shopping', 'Travel', 'Bills',
  'Entertainment', 'Healthcare', 'Education', 'Salary', 'Other'];

export default function Transactions() {
  const { data, loading, error, reload } = useFetch(transactionsApi.list);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [kind, setKind] = useState('All');

  const rows = useMemo(() => (data ?? []).filter((t) =>
    (category === 'All' || t.category === category)
    && (kind === 'All' || t.type === kind.toLowerCase())
    && `${t.description} ${t.category}`.toLowerCase().includes(query.toLowerCase())),
  [data, query, category, kind]);

  const remove = async (id: number) => {
    await transactionsApi.remove(id);
    reload();
  };

  if (loading) return <Skeleton rows={5} />;
  if (error) return <ErrorState message={error} onRetry={reload} />;

  return (
    <>
      <PageHeader title="Transactions"
        subtitle={`${rows.length} of ${data?.length ?? 0} transactions.`} />
      <div className="card">
        <div className="mb-4 flex flex-wrap gap-3">
          <input className="input sm:w-64" placeholder="Search…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          <select className="input sm:w-40" value={category}
            onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select className="input sm:w-36" value={kind}
            onChange={(e) => setKind(e.target.value)}>
            {['All', 'Income', 'Expense'].map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>

        {rows.length === 0 ? <EmptyState message="No transactions match these filters." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="label">
                  <th className="py-2 text-left">Date</th>
                  <th className="py-2 text-left">Description</th>
                  <th className="py-2 text-left">Category</th>
                  <th className="py-2 text-right">Amount</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-3 text-slate-500">{t.date}</td>
                    <td className="py-3">{t.description}</td>
                    <td className="py-3"><span className="chip">{t.category}</span></td>
                    <td className={`py-3 text-right font-semibold ${t.amount > 0 ? 'text-emerald-600' : ''}`}>
                      {t.amount > 0 ? '+' : '−'}{formatINR(t.amount)}
                    </td>
                    <td className="py-3 pl-3 text-right">
                      <button onClick={() => remove(t.id)} aria-label="Delete"
                        className="text-slate-400 hover:text-red-500">
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
