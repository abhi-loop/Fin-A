import axios from 'axios';
import type {
  Alert, BudgetLine, ChatResponse, DashboardData, Goal, Holding, Transaction,
} from '../types';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api',
  timeout: 60_000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('finagent_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const authApi = {
  login: (email: string, password: string) =>
    client.post<{ token: string; user: { id: number; name: string; email: string } }>(
      '/auth/login', { email, password },
    ).then((r) => r.data),
  register: (name: string, email: string, password: string) =>
    client.post('/auth/register', { name, email, password }).then((r) => r.data),
};

export const dashboardApi = {
  get: () => client.get<DashboardData>('/dashboard').then((r) => r.data),
};

export const transactionsApi = {
  list: () => client.get<Transaction[]>('/transactions').then((r) => r.data),
  create: (body: Omit<Transaction, 'id' | 'date'> & { date?: string }) =>
    client.post<Transaction>('/transactions', body).then((r) => r.data),
  update: (id: number, body: Omit<Transaction, 'id'>) =>
    client.put<Transaction>(`/transactions/${id}`, body).then((r) => r.data),
  remove: (id: number) => client.delete(`/transactions/${id}`),
};

export const budgetApi = {
  get: () => client.get<{ budget: BudgetLine[]; total_budget: number }>('/budget')
    .then((r) => r.data),
};

export const goalsApi = {
  list: () => client.get<{ goals: Goal[] }>('/goals').then((r) => r.data.goals),
};

export const investmentsApi = {
  get: () => client.get<{
    holdings: Holding[]; total_invested: number;
    total_current: number; unrealised_gain: number;
  }>('/investments').then((r) => r.data),
};

export const alertsApi = {
  list: () => client.get<Alert[]>('/alerts').then((r) => r.data),
  markRead: (id: number) => client.put(`/alerts/${id}/read`),
};

export const aiApi = {
  chat: (message: string) =>
    client.post<ChatResponse>('/ai/chat', { message }).then((r) => r.data),
};

export const formatINR = (n: number) =>
  `₹${Math.round(Math.abs(n)).toLocaleString('en-IN')}`;
