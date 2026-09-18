import { useRef, useState } from 'react';
import { AlertCircle, BarChart2, Brain, Send, Sparkles, TrendingUp } from 'lucide-react';
import AnalysisCard from '../components/ai/AnalysisCard';
import { PageHeader } from '../components/common';
import { aiApi } from '../services/api';
import type { ChatMessage } from '../types';

const SUGGESTIONS = [
  { text: 'Should I buy \u20b95,000 of Reliance stock?', icon: TrendingUp, path: 'investment' },
  { text: 'I spent \u20b9800 on groceries today', icon: BarChart2, path: 'expense' },
  { text: 'Am I overspending this month?', icon: BarChart2, path: 'budget' },
  { text: 'Can I afford a \u20b915,000 phone?', icon: TrendingUp, path: 'investment' },
  { text: 'How much did I spend on food?', icon: BarChart2, path: 'budget' },
  { text: 'Am I on track for my savings goal?', icon: Brain, path: 'goal' },
];

const PATH_COLORS: Record<string, string> = {
  investment: 'hover:border-emerald-500 hover:text-emerald-400',
  expense: 'hover:border-blue-500 hover:text-blue-400',
  budget: 'hover:border-amber-500 hover:text-amber-400',
  goal: 'hover:border-purple-500 hover:text-purple-400',
};

function getLoadingText(question: string) {
  const q = question.toLowerCase();
  if (/buy|invest|stock|ipo|share|fund|afford/i.test(q))
    return 'Running agentic investment analysis\u2026';
  if (/spent|paid|bought|expense/i.test(q))
    return 'Logging expense and checking budget\u2026';
  return 'Analysing your finances\u2026';
}

function IntentBadge({ intent }: { intent?: string }) {
  if (!intent) return null;
  const map: Record<string, { label: string; color: string }> = {
    investment_query: { label: 'Investment Analysis', color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
    ipo_alert: { label: 'IPO Analysis', color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
    goal_planning: { label: 'Goal Planning', color: 'text-purple-400 border-purple-500/30 bg-purple-500/10' },
    expense_log: { label: 'Expense Logged', color: 'text-blue-400 border-blue-500/30 bg-blue-500/10' },
    budget_query: { label: 'Budget Check', color: 'text-amber-400 border-amber-500/30 bg-amber-500/10' },
    out_of_scope: { label: 'Out of Scope', color: 'text-slate-400 border-slate-500/30 bg-slate-500/10' },
  };
  const cfg = map[intent];
  if (!cfg) return null;
  return (
    <span className={`mb-1 inline-block rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

export default function Assistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadingText, setLoadingText] = useState('Analysing your finances\u2026');
  const endRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setInput('');
    setBusy(true);
    setLoadingText(getLoadingText(question));
    setMessages((m) => [...m, { role: 'user', text: question },
      { role: 'assistant', loading: true }]);

    try {
      const data = await aiApi.chat(question);
      setMessages((m) => [...m.slice(0, -1), { role: 'assistant', data }]);
    } catch {
      setMessages((m) => [...m.slice(0, -1), {
        role: 'assistant', error: true,
        text: 'I could not reach the analysis service. Check that the backend is running.',
      }]);
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="AI Financial Assistant"
        subtitle="Ask about investments, log expenses, or check your budget \u2014 powered by a two-path agent."
      />

      {/* Suggestion chips */}
      <div className="mb-6 flex flex-wrap gap-2">
        {SUGGESTIONS.map(({ text, path }) => (
          <button
            key={text}
            onClick={() => send(text)}
            disabled={busy}
            className={`chip transition-colors disabled:opacity-50 ${PATH_COLORS[path] ?? ''}`}
          >
            {text}
          </button>
        ))}
      </div>

      {/* Empty state */}
      {messages.length === 0 && (
        <div className="card flex flex-col gap-3 text-sm text-slate-500 dark:text-slate-400">
          <div className="flex items-center gap-3">
            <Sparkles size={18} className="text-brand" />
            <span>Every number is fetched from your accounts by the agent \u2014 nothing is guessed.</span>
          </div>
          <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5">
              <p className="mb-0.5 font-semibold text-emerald-400">Investment Path</p>
              <p>Calls 3 tools \u2192 confidence scorer \u2192 verdict + reasoning</p>
            </div>
            <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-2.5">
              <p className="mb-0.5 font-semibold text-blue-400">Expense Path</p>
              <p>Logs directly to DB, recomputes budget, fires alert if &gt;85%</p>
            </div>
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
              <p className="mb-0.5 font-semibold text-amber-400">Budget Path</p>
              <p>Deterministic \u2014 no LLM, just your real numbers</p>
            </div>
          </div>
        </div>
      )}

      {/* Message thread */}
      <div className="flex flex-col gap-4">
        {messages.map((m, i) => {
          if (m.role === 'user') {
            return (
              <div key={i} className="self-end rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-white max-w-[85%]">
                {m.text}
              </div>
            );
          }
          if (m.loading) {
            return (
              <div key={i} className="flex flex-col gap-1">
                <div className="card w-fit animate-pulse rounded-bl-md text-sm text-slate-500 flex items-center gap-2">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-brand" style={{ animationDelay: '0ms' }} />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-brand" style={{ animationDelay: '150ms' }} />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-brand" style={{ animationDelay: '300ms' }} />
                  <span className="ml-1">{loadingText}</span>
                </div>
              </div>
            );
          }
          if (m.error) {
            return (
              <div key={i} className="card rounded-bl-md text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
                <AlertCircle size={16} />
                {m.text}
              </div>
            );
          }
          return (
            <div key={i} className="flex flex-col gap-1">
              {m.data?.intent && <IntentBadge intent={m.data.intent} />}
              <AnalysisCard data={m.data!} />
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      {/* Input bar */}
      <div className="sticky bottom-4 mt-6 flex gap-2">
        <input
          className="input"
          placeholder="Ask about an investment, log an expense, or check your budget\u2026"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(input)}
        />
        <button className="btn" onClick={() => send(input)} disabled={busy}>
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
