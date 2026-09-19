import { AlertTriangle, BadgeCheck, ExternalLink, ShieldAlert, Star, Store } from 'lucide-react';
import type { ChatResponse } from '../../types';

// Save as frontend/src/components/ai/PriceCompareCard.tsx
// Self-contained: no changes to types/index.ts are needed for this file.

export interface PriceOffer {
  store: string;
  title: string;
  price: number;
  link: string;
  rating?: number | null;
  rating_count?: number | null;
  delivery?: string | null;
  image?: string | null;
}

export interface PriceComparison {
  query: string;
  live: boolean;
  currency: string;
  offers: PriceOffer[];
  stats?: {
    count: number;
    best_price: number;
    average_price: number;
    highest_price: number;
    save_vs_average: number;
    save_vs_highest: number;
    save_pct_vs_average: number;
  };
  affordability?: {
    affordable: boolean;
    remaining_after: number;
    balance: number;
    months_to_afford: number | null;
  } | null;
  search_links: { store: string; link: string }[];
  note?: string | null;
  error?: string | null;
  max_price?: number | null;
}

type Props = { data: ChatResponse & { comparison?: PriceComparison } };

const inr = (n: number) => '\u20b9' + Math.round(n).toLocaleString('en-IN');

// Only ever link to http(s) URLs coming back from the API.
const safeHref = (u: string) => (/^https?:\/\//i.test(u) ? u : '#');

export default function PriceCompareCard({ data }: Props) {
  const c = data.comparison!;
  const offers = c.offers ?? [];
  const best = offers[0];
  const s = c.stats;
  const a = c.affordability;

  return (
    <div className="card w-full rounded-bl-md">
      <p className="label mb-2">Price comparison &middot; {c.query}</p>

      {/* Best price hero */}
      {best && s ? (
        <div className="rounded-2xl border border-emerald-500/40 bg-gradient-to-br from-emerald-500/20 to-emerald-600/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-widest text-emerald-400">
                Best price
              </p>
              <p className="text-3xl font-extrabold tracking-tight">{inr(best.price)}</p>
              <p className="text-sm text-slate-500 dark:text-slate-400">at {best.store}</p>
            </div>

            {s.count > 1 && s.save_vs_average > 0 && (
              <div className="rounded-xl bg-emerald-500 px-3 py-2 text-white shadow-lg shadow-emerald-500/30">
                <p className="text-[10px] font-semibold uppercase tracking-wide">You save</p>
                <p className="text-lg font-bold leading-tight">{inr(s.save_vs_average)}</p>
                <p className="text-[10px]">vs average ({s.save_pct_vs_average}%)</p>
              </div>
            )}

            <a
              href={safeHref(best.link)}
              target="_blank"
              rel="noopener noreferrer"
              className="btn inline-flex items-center gap-1"
            >
              View deal <ExternalLink size={14} />
            </a>
          </div>
        </div>
      ) : (
        <p className="leading-relaxed">{data.answer}</p>
      )}

      {/* Affordability */}
      {a && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-xl border px-3 py-2 text-sm ${
            a.affordable
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500'
              : 'border-purple-500/30 bg-purple-500/10 text-purple-400'
          }`}
        >
          {a.affordable ? <BadgeCheck size={16} className="mt-0.5" /> : <ShieldAlert size={16} className="mt-0.5" />}
          <span>
            {a.affordable
              ? `You can afford this and would keep ${inr(a.remaining_after)} after upcoming expenses.`
              : `Above your available money after upcoming expenses${
                  a.months_to_afford ? ` (about ${a.months_to_afford} month(s) of savings away)` : ''
                }.`}
          </span>
        </div>
      )}

      {c.note && <p className="mt-2 text-xs text-amber-500">{c.note}</p>}

      {/* Ranked offers */}
      {offers.length > 0 && (
        <ul className="mt-4 divide-y divide-slate-200 rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
          {offers.map((o, i) => (
            <li key={`${o.store}-${i}`} className="flex items-center gap-3 px-3 py-2.5">
              <span className="w-5 text-center text-xs font-bold text-slate-400">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1 text-sm font-semibold">
                  <Store size={12} className="shrink-0 text-slate-400" />
                  <span className="truncate">{o.store}</span>
                  {i === 0 && (
                    <span className="ml-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-500">
                      Cheapest
                    </span>
                  )}
                </p>
                <p className="truncate text-xs text-slate-500 dark:text-slate-400">{o.title}</p>
                {o.rating ? (
                  <p className="mt-0.5 flex items-center gap-1 text-[11px] text-amber-500">
                    <Star size={11} fill="currentColor" /> {o.rating}
                    {o.rating_count ? (
                      <span className="text-slate-400">({o.rating_count.toLocaleString('en-IN')})</span>
                    ) : null}
                  </p>
                ) : null}
              </div>
              <div className="text-right">
                <p className="text-sm font-bold">{inr(o.price)}</p>
                {i > 0 && best && (
                  <p className="text-[11px] text-slate-400">+{inr(o.price - best.price)}</p>
                )}
              </div>
              <a
                href={safeHref(o.link)}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open ${o.store}`}
                className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:text-emerald-500 dark:border-slate-700"
              >
                <ExternalLink size={14} />
              </a>
            </li>
          ))}
        </ul>
      )}

      {/* No live prices: still give working store-search links */}
      {offers.length === 0 && (
        <div className="mt-3">
          <p className="flex items-start gap-2 text-sm">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
            <span>{data.answer}</span>
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(c.search_links ?? []).map((l) => (
              <a
                key={l.store}
                href={safeHref(l.link)}
                target="_blank"
                rel="noopener noreferrer"
                className="chip flex items-center gap-1"
              >
                {l.store} <ExternalLink size={12} />
              </a>
            ))}
          </div>
        </div>
      )}

      <p className="mt-4 text-[11px] text-slate-400">
        Prices from Google Shopping at the time you asked. Check stock, delivery and the final
        price on the store page before you buy.
      </p>
    </div>
  );
}