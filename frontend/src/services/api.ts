import axios from 'axios';
import type {
  Alert,
  BudgetLine,
  ChatResponse,
  DashboardData,
  Goal,
  Holding,
  Transaction,
} from '../types';

import { supabase } from '../lib/supabase';

import {
  demoAlerts,
  demoBudget,
  demoChatResponse,
  demoDashboard,
  demoGoals,
  demoHoldings,
  demoTransactions,
} from './demoData';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api',
  timeout: 60_000,
});

// Inject Supabase JWT into every request
client.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }

  return config;
});

export const authApi = {
  // Sync ensures the backend User row exists after Supabase signup
  sync: (name: string) =>
    client.post('/auth/sync', { name }).then((r) => r.data),

  login: (
    email: string,
    password: string,
  ) =>
    client
      .post<{
        token: string;
        user: {
          id: number;
          name: string;
          email: string;
        };
      }>('/auth/login', { email, password })
      .then((r) => r.data),

  register: (
    name: string,
    email: string,
    password: string,
  ) =>
    client
      .post('/auth/register', { name, email, password })
      .then((r) => r.data),

  isUnavailable: (error: unknown) =>
    axios.isAxiosError(error) && !error.response,
};

export const dashboardApi = {
  get: () =>
    client
      .get<DashboardData>('/dashboard')
      .then((r) => r.data)
      .catch((error) => {
        if (authApi.isUnavailable(error)) return demoDashboard;
        throw error;
      }),
};

export const transactionsApi = {
  list: () =>
    client
      .get<Transaction[]>('/transactions')
      .then((r) => r.data)
      .catch((error) => {
        if (authApi.isUnavailable(error)) return demoTransactions;
        throw error;
      }),

  create: (
    body: Omit<Transaction, 'id' | 'date'> & { date?: string },
  ) =>
    client
      .post<Transaction>('/transactions', body)
      .then((r) => r.data),

  update: (
    id: number,
    body: Omit<Transaction, 'id'>,
  ) =>
    client
      .put<Transaction>(`/transactions/${id}`, body)
      .then((r) => r.data),

  remove: (id: number) =>
    client.delete(`/transactions/${id}`),
};

export const budgetApi = {
  get: () =>
    client
      .get<{
        budget: BudgetLine[];
        total_budget: number;
      }>('/budget')
      .then((r) => r.data)
      .catch((error) => {
        if (authApi.isUnavailable(error)) {
          return {
            budget: demoBudget,
            total_budget: demoBudget.reduce(
              (sum, item) => sum + item.limit,
              0,
            ),
          };
        }

        throw error;
      }),
};

export const goalsApi = {
  list: () =>
    client
      .get<{ goals: Goal[] }>('/goals')
      .then((r) => r.data.goals)
      .catch((error) => {
        if (authApi.isUnavailable(error)) return demoGoals;
        throw error;
      }),
};

export const investmentsApi = {
  get: () =>
    client
      .get<{
        holdings: Holding[];
        total_invested: number;
        total_current: number;
        unrealised_gain: number;
      }>('/investments')
      .then((r) => r.data)
      .catch((error) => {
        if (authApi.isUnavailable(error)) {
          const totalInvested = demoHoldings.reduce(
            (sum, item) => sum + item.invested,
            0,
          );

          const totalCurrent = demoHoldings.reduce(
            (sum, item) => sum + item.current,
            0,
          );

          return {
            holdings: demoHoldings,
            total_invested: totalInvested,
            total_current: totalCurrent,
            unrealised_gain: totalCurrent - totalInvested,
          };
        }

        throw error;
      }),
};

export const alertsApi = {
  list: () =>
    client
      .get<Alert[]>('/alerts')
      .then((r) => r.data)
      .catch((error) => {
        if (authApi.isUnavailable(error)) return demoAlerts;
        throw error;
      }),

  markRead: (id: number) =>
    client.put(`/alerts/${id}/read`),
};

// AI AGENT
export const aiApi = {
  chat: (message: string) =>
    client
      .post<ChatResponse>('/ai/chat', { message })
      .then((r) => r.data)
      .catch((error) => {
        if (authApi.isUnavailable(error)) {
          return demoChatResponse(message);
        }

        throw error;
      }),
};

export const formatINR = (n: number) =>
  `₹${Math.round(Math.abs(n)).toLocaleString('en-IN')}`;