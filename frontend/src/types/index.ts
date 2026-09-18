export type Category =
  | 'Food' | 'Shopping' | 'Travel' | 'Bills' | 'Entertainment'
  | 'Healthcare' | 'Education' | 'Salary' | 'Other';

export interface Transaction {
  id: number;
  amount: number;
  type: 'income' | 'expense';
  category: Category | string;
  description: string;
  date: string;
}

export interface BudgetLine {
  category: string;
  limit: number;
  spent: number;
  remaining: number;
  used_pct: number;
}

export interface Goal {
  name: string;
  target: number;
  saved: number;
  remaining: number;
  progress_pct: number;
  deadline: string;
}

export interface Holding {
  asset: string;
  type: string;
  invested: number;
  current: number;
}

export interface Alert {
  id: number;
  title: string;
  message: string;
  severity: 'low' | 'med' | 'high';
  category: string;
  read: boolean;
  createdAt: string;
}

export interface DashboardData {
  user: { name: string };
  balance: number;
  income: number;
  expenses: number;
  savings: number;
  savingsRatePct: number;
  spendingByCategory: Record<string, number>;
  budget: BudgetLine[];
  goals: Goal[];
  recentTransactions: Pick<Transaction, 'date' | 'description' | 'category' | 'amount'>[];
  alerts: { title: string; message: string; severity: string }[];
  trend: number[];
}

export interface Metric { label: string; value: string }

export interface ChatResponse {
  answer: string;
  metrics: Metric[];
  insights: string[];
  sources: string[];
  tools_used?: string[];
  // Investment / agentic path extras
  verdict?: 'buy' | 'hold' | 'avoid' | 'insufficient_funds';
  confidence?: number;         // 0-100
  reasoning?: string[];
  caveats?: string[];
  intent?: string;             // which path handled this
  alert_fired?: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text?: string;
  data?: ChatResponse;
  loading?: boolean;
  error?: boolean;
}
