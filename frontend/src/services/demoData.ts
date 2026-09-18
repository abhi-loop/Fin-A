import type {
  Alert, BudgetLine, ChatResponse, DashboardData, Goal, Holding, Transaction,
} from '../types';

export const demoUser = { id: 1, name: 'Demo User', email: 'demo@finagent.in' };

export const demoTransactions: Transaction[] = [
  { id: 1, date: '2026-09-15', description: 'Salary credited', category: 'Salary', amount: 85000, type: 'income' },
  { id: 2, date: '2026-09-14', description: 'Apartment rent', category: 'Bills', amount: -22000, type: 'expense' },
  { id: 3, date: '2026-09-12', description: 'Grocery shopping', category: 'Food', amount: -4250, type: 'expense' },
  { id: 4, date: '2026-09-10', description: 'Index fund SIP', category: 'Other', amount: -10000, type: 'expense' },
  { id: 5, date: '2026-09-08', description: 'Weekend trip', category: 'Travel', amount: -6800, type: 'expense' },
  { id: 6, date: '2026-09-05', description: 'Electricity bill', category: 'Bills', amount: -1850, type: 'expense' },
];

export const demoBudget: BudgetLine[] = [
  { category: 'Food', limit: 10000, spent: 6250, remaining: 3750, used_pct: 62.5 },
  { category: 'Bills', limit: 28000, spent: 23850, remaining: 4150, used_pct: 85.2 },
  { category: 'Travel', limit: 12000, spent: 6800, remaining: 5200, used_pct: 56.7 },
  { category: 'Entertainment', limit: 5000, spent: 2100, remaining: 2900, used_pct: 42 },
];

export const demoGoals: Goal[] = [
  { name: 'Emergency fund', target: 150000, saved: 97500, remaining: 52500, progress_pct: 65, deadline: 'Mar 2027' },
  { name: 'New laptop', target: 90000, saved: 54000, remaining: 36000, progress_pct: 60, deadline: 'Dec 2026' },
];

export const demoAlerts: Alert[] = [
  { id: 1, title: 'Bills are nearing their limit', message: 'You have used 85% of your monthly bills budget.', severity: 'med', category: 'Budget', read: false, createdAt: '2026-09-15T10:00:00Z' },
  { id: 2, title: 'Savings goal on track', message: 'Your emergency fund is progressing well this month.', severity: 'low', category: 'Goals', read: false, createdAt: '2026-09-12T10:00:00Z' },
];

export const demoDashboard: DashboardData = {
  user: { name: demoUser.name },
  balance: 284600,
  income: 85000,
  expenses: 48200,
  savings: 36800,
  savingsRatePct: 43.3,
  spendingByCategory: { Bills: 23850, Food: 6250, Travel: 6800, Entertainment: 2100, Other: 9200 },
  budget: demoBudget,
  goals: demoGoals,
  recentTransactions: demoTransactions.slice(1, 6),
  alerts: demoAlerts.map(({ title, message, severity }) => ({ title, message, severity })),
  trend: [42000, 46500, 39800, 51200, 44700, 48200],
};

export const demoHoldings: Holding[] = [
  { asset: 'Nifty 50 Index Fund', type: 'Mutual fund', invested: 85000, current: 94200 },
  { asset: 'HDFC Flexi Cap Fund', type: 'Mutual fund', invested: 60000, current: 67200 },
  { asset: 'Government Bonds', type: 'Bond', invested: 40000, current: 41800 },
];

export const demoChatResponse = (question: string): ChatResponse => {
  const q = question.toLowerCase();

  // Investment / agentic path demo
  if (/buy|invest|stock|share|fund|ipo|reliance|apple|nifty/i.test(q)) {
    const m = q.match(/\d[\d,]*/);
    const amount = m ? parseInt(m[0].replace(/,/g, '')) : 5000;
    const amtStr = '\u20b9' + amount.toLocaleString('en-IN');
    return {
      answer: `Based on your demo profile, a ${amtStr} investment is manageable given your current balance of \u20b92,84,600 and monthly savings of \u20b936,800. Always verify the live market price before acting.`,
      metrics: [
        { label: 'Balance', value: '\u20b92,84,600' },
        { label: 'Monthly Savings', value: '\u20b936,800' },
        { label: 'Budget Headroom', value: '\u20b915,100' },
        { label: 'Confidence', value: '62%' },
      ],
      insights: [
        'Amount fits within available budget headroom.',
        'Risk tolerance is moderate \u2014 equity exposure is appropriate.',
      ],
      sources: ['User Profile', 'Market Data (Demo)', 'Spending History'],
      tools_used: ['get_user_profile', 'web_search', 'get_spending_history'],
      verdict: 'hold',
      confidence: 62,
      reasoning: [
        `The amount ${amtStr} fits within your budget headroom of \u20b915,100.`,
        'Your monthly savings rate of 43.3% indicates healthy cash flow.',
        'Live market data is unavailable in demo mode \u2014 price verification needed.',
      ],
      caveats: [
        'Live price data is mocked \u2014 verify current price before investing.',
        'Past performance is not a guarantee of future returns.',
      ],
      intent: 'investment_query',
      alert_fired: false,
    };
  }

  // Expense log demo
  if (/spent|paid|bought|expense/i.test(q)) {
    return {
      answer: 'Expense logged. Your balance has been updated and budget tracking is current.',
      metrics: [
        { label: 'Amount Logged', value: '\u20b9800' },
        { label: 'New Balance', value: '\u20b92,83,800' },
        { label: 'Monthly Savings', value: '\u20b936,000' },
        { label: 'Food Budget Used', value: '68.5%' },
      ],
      insights: ['Expense recorded in Food for today.', 'Savings rate this month: 42.4%.'],
      sources: ['Transactions', 'Budget'],
      tools_used: ['expense_log', 'get_budget'],
      intent: 'expense_log',
      alert_fired: false,
    };
  }

  // Default / budget query demo
  return {
    answer: `Your finances look healthy. You have \u20b936,800 left after this month\u2019s expenses. A \u20b915,000 purchase would be manageable while keeping your savings goals on track.`,
    metrics: [
      { label: 'Monthly savings', value: '\u20b936,800' },
      { label: 'Savings rate', value: '43.3%' },
    ],
    insights: [`You asked: "${question}"`, 'Preview response using local demo data.'],
    sources: ['Demo dashboard data'],
    intent: 'budget_query',
  };
};
