import { CheckCircle2 } from 'lucide-react';
import type { ChatResponse } from '../../types';

export default function AnalysisCard({ data }: { data: ChatResponse }) {
  return (
    <div className="card w-full rounded-bl-md">
      <p className="label mb-2">Financial Analysis</p>
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
