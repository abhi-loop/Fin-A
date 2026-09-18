import { Link } from 'react-router-dom';
import { ArrowRight, BarChart3, ShieldCheck, Sparkles } from 'lucide-react';

const FEATURES = [
  { Icon: Sparkles, title: 'Ask, don\u2019t dig',
    body: 'Ask “Can I afford a ₹15,000 phone?” and get a real answer with the maths shown.' },
  { Icon: ShieldCheck, title: 'Grounded in your data',
    body: 'The agent calls tools on your accounts. It never invents a number.' },
  { Icon: BarChart3, title: 'Everything in one place',
    body: 'Spending, budgets, goals and investments in a single view.' },
];

export default function Landing() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-20">
      <p className="text-lg font-bold">Fin<span className="text-brand">Agent</span></p>
      <h1 className="mt-10 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
        Your money, explained.
      </h1>
      <p className="mt-4 max-w-xl text-lg text-slate-600 dark:text-slate-400">
        An intelligent financial decision agent that reads your real financial
        situation and answers the questions you actually ask.
      </p>
      <div className="mt-8 flex gap-3">
        <Link to="/login" className="btn flex items-center gap-2">
          Open the demo <ArrowRight size={16} />
        </Link>
        <Link to="/register" className="btn-ghost">Create account</Link>
      </div>

      <div className="mt-20 grid gap-4 md:grid-cols-3">
        {FEATURES.map(({ Icon, title, body }) => (
          <div key={title} className="card">
            <Icon size={20} className="text-brand" />
            <p className="mt-3 font-semibold">{title}</p>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
