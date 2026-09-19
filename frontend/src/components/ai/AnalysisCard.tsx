
import { CheckCircle2 } from 'lucide-react';
import type { ChatResponse } from '../../types';
import RecommendationCard from './RecommendationCard';
import PriceCompareCard from './PriceCompareCard';

export default function AnalysisCard({ data }: { data: ChatResponse }) {

  const comparison = (data as ChatResponse & { comparison?: unknown }).comparison;
if (comparison) {
  return <PriceCompareCard data={data} />;
}

  // Investment / agentic path → render the full Recommendation Card
  if (data.verdict) {
    return <RecommendationCard data={data} />;
  }

  // Structured path (expense log, budget query) → metrics / insights layout
  return (
    <div className="card w-full rounded-bl-md">
      {/* Intent badge */}
      {data.intent && (
        <p className="mb-2 inline-block rounded-full border border-slate-700 bg-slate-800/60
                       px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          {data.intent === 'expense_log' ? 'Expense Logged'
            : data.intent === 'budget_query' ? 'Budget Check'
            : data.intent === 'goal_planning' ? 'Goal Planning'
            : 'Financial Analysis'}
        </p>
      )}
      {!data.intent && <p className="label mb-2">Financial Analysis</p>}

      <p className="leading-relaxed">{data.answer}</p>

      {data.metrics.length > 0 && (
        <div className="my-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {data.metrics.map((m) => (
            <div
              key={m.label}
              className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-[#0c0f14]"
            >
              <p className="text-[11px] text-slate-500 dark:text-slate-400">{m.label}</p>
              <p className="mt-0.5 text-lg font-bold tracking-tight">{m.value}</p>
            </div>
          ))}
        </div>
      )}

      {data.insights.length > 0 && (
        <>
          <p className="mb-1 text-sm font-semibold">AI Insight</p>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {data.insights.map((i) => <li key={i}>{i}</li>)}
          </ul>
        </>
      )}

      {data.sources.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {data.sources.map((s) => (
            <span key={s} className="chip flex items-center gap-1">
              <CheckCircle2 size={12} /> {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
