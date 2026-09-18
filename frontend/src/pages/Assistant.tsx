import { useRef, useState } from 'react';
import { Send, Sparkles } from 'lucide-react';
import AnalysisCard from '../components/ai/AnalysisCard';
import { PageHeader } from '../components/common';
import { aiApi } from '../services/api';
import type { ChatMessage } from '../types';

const SUGGESTIONS = [
  'Can I afford a ₹15,000 phone this month?',
  'Where did most of my money go this month?',
  'Am I overspending?',
  'How much can I save this month?',
  'Am I on track for my savings goal?',
  'How much did I spend on food?',
];

export default function Assistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    setInput('');
    setBusy(true);
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
        subtitle="Ask questions about your money, spending, budgets and goals."
      />

      <div className="mb-6 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            disabled={busy}
            className="chip transition-colors hover:border-brand hover:text-brand disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>

      {messages.length === 0 && (
        <div className="card flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
          <Sparkles size={18} className="text-brand" />
          Every number below is fetched from your accounts by the agent — nothing is guessed.
        </div>
      )}

      <div className="flex flex-col gap-4">
        {messages.map((m, i) => {
          if (m.role === 'user') {
            return (
              <div key={i} className="self-end rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-white">
                {m.text}
              </div>
            );
          }
          if (m.loading) {
            return (
              <div key={i} className="card w-fit animate-pulse rounded-bl-md text-sm text-slate-500">
                Analyzing your finances…
              </div>
            );
          }
          if (m.error) {
            return (
              <div key={i} className="card rounded-bl-md text-sm text-red-600 dark:text-red-400">
                {m.text}
              </div>
            );
          }
          return <AnalysisCard key={i} data={m.data!} />;
        })}
        <div ref={endRef} />
      </div>

      <div className="sticky bottom-4 mt-6 flex gap-2">
        <input
          className="input"
          placeholder="Ask anything about your finances…"
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
