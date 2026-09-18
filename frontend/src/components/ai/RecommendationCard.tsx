import { AlertTriangle, CheckCircle2, Info, ShieldAlert, TrendingDown, TrendingUp, Zap } from 'lucide-react';
import type { ChatResponse } from '../../types';

// ─── Verdict Config ──────────────────────────────────────────────────────────

const VERDICT_CONFIG = {
  buy: {
    label: 'BUY',
    icon: TrendingUp,
    bg: 'from-emerald-500/20 to-emerald-600/10',
    border: 'border-emerald-500/40',
    badge: 'bg-emerald-500 text-white shadow-emerald-500/30',
    ring: '#10b981',
    text: 'text-emerald-400',
  },
  hold: {
    label: 'HOLD',
    icon: Zap,
    bg: 'from-amber-500/20 to-amber-600/10',
    border: 'border-amber-500/40',
    badge: 'bg-amber-500 text-white shadow-amber-500/30',
    ring: '#f59e0b',
    text: 'text-amber-400',
  },
  avoid: {
    label: 'AVOID',
    icon: TrendingDown,
    bg: 'from-red-500/20 to-red-600/10',
    border: 'border-red-500/40',
    badge: 'bg-red-500 text-white shadow-red-500/30',
    ring: '#ef4444',
    text: 'text-red-400',
  },
  insufficient_funds: {
    label: 'INSUFFICIENT FUNDS',
    icon: ShieldAlert,
    bg: 'from-purple-500/20 to-purple-600/10',
    border: 'border-purple-500/40',
    badge: 'bg-purple-500 text-white shadow-purple-500/30',
    ring: '#a855f7',
    text: 'text-purple-400',
  },
} as const;

// ─── Confidence Ring SVG ─────────────────────────────────────────────────────

function ConfidenceRing({ confidence, color }: { confidence: number; color: string }) {
  const r = 36;
  const circ = 2 * Math.PI * r;
  const filled = circ * (confidence / 100);

  return (
    <div className="relative flex h-24 w-24 items-center justify-center">
      <svg width="96" height="96" className="-rotate-90">
        {/* Background track */}
        <circle cx="48" cy="48" r={r} fill="none" strokeWidth="8"
          stroke="rgba(255,255,255,0.06)" />
        {/* Filled arc */}
        <circle cx="48" cy="48" r={r} fill="none" strokeWidth="8"
          stroke={color}
          strokeDasharray={`${filled} ${circ - filled}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.8s ease', filter: `drop-shadow(0 0 6px ${color}80)` }}
        />
      </svg>
      <div className="absolute text-center">
        <p className="text-xl font-black leading-none" style={{ color }}>{confidence}</p>
        <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-500">conf.</p>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function RecommendationCard({ data }: { data: ChatResponse }) {
  const verdict = data.verdict ?? 'hold';
  const cfg = VERDICT_CONFIG[verdict as keyof typeof VERDICT_CONFIG] ?? VERDICT_CONFIG.hold;
  const VerdictIcon = cfg.icon;
  const confidence = data.confidence ?? 50;

  return (
    <div className={`w-full overflow-hidden rounded-2xl rounded-bl-md border bg-gradient-to-br ${cfg.bg} ${cfg.border} backdrop-blur-sm`}>

      {/* ── Header: Verdict badge + Confidence ring ── */}
      <div className="flex items-center justify-between gap-4 p-5 pb-3">
        <div className="flex flex-col gap-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
            AI Recommendation
          </p>
          <div className={`flex w-fit items-center gap-2 rounded-lg px-4 py-2 text-sm font-black uppercase tracking-wider shadow-lg ${cfg.badge}`}>
            <VerdictIcon size={16} />
            {cfg.label}
          </div>
          {data.alert_fired && (
            <div className="flex items-center gap-1.5 rounded-md border border-orange-500/30 bg-orange-500/10 px-2.5 py-1 text-xs font-semibold text-orange-400">
              <AlertTriangle size={12} />
              Alert triggered — check your notifications
            </div>
          )}
        </div>
        <ConfidenceRing confidence={confidence} color={cfg.ring} />
      </div>

      {/* ── Answer ── */}
      <div className="px-5 pb-3">
        <p className="leading-relaxed text-sm text-slate-300">{data.answer}</p>
      </div>

      {/* ── Metrics grid ── */}
      {data.metrics.length > 0 && (
        <div className="mx-5 mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {data.metrics.map((m) => (
            <div key={m.label}
              className="rounded-xl border border-white/8 bg-black/20 p-3 backdrop-blur-sm">
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wide">{m.label}</p>
              <p className="mt-0.5 text-base font-bold tracking-tight text-white">{m.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Reasoning ── */}
      {(data.reasoning && data.reasoning.length > 0) && (
        <div className="mx-5 mb-4">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
            <Info size={12} className={cfg.text} /> Why this verdict
          </p>
          <ol className="space-y-1.5">
            {data.reasoning.map((r, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-slate-300">
                <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-black ${cfg.badge}`}>
                  {i + 1}
                </span>
                {r}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* ── Caveats ── */}
      {(data.caveats && data.caveats.length > 0) && (
        <div className="mx-5 mb-4 rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-yellow-500/80">
            <AlertTriangle size={12} /> Caveats
          </p>
          <ul className="space-y-1">
            {data.caveats.map((c, i) => (
              <li key={i} className="text-xs text-slate-400">{c}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Footer: sources + tools used ── */}
      <div className="flex flex-wrap items-center gap-2 border-t border-white/5 px-5 py-3">
        {data.sources.map((s) => (
          <span key={s}
            className="flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-0.5 text-[11px] text-slate-400">
            <CheckCircle2 size={10} className="text-emerald-500" /> {s}
          </span>
        ))}
        {(data.tools_used && data.tools_used.length > 0) && (
          <span className="ml-auto rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-0.5 text-[10px] text-slate-500">
            {data.tools_used.length} tools
          </span>
        )}
      </div>
    </div>
  );
}
