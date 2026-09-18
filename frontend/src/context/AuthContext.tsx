import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
<<<<<<< Updated upstream
import type { Session, User as SupabaseUser } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
=======
import { authApi } from '../services/api';
import { demoUser } from '../services/demoData';
>>>>>>> Stashed changes

interface User { id: string; name: string; email: string }

interface AuthValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

/** Map a Supabase user into our app's User shape */
function toAppUser(su: SupabaseUser): User {
  return {
    id: su.id,
    name: su.user_metadata?.name ?? su.email?.split('@')[0] ?? '',
    email: su.email ?? '',
  };
}

/** After login/register, ensure a User row exists in our backend DB */
async function syncUserToBackend(session: Session) {
  try {
    await fetch(
      (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api') + '/auth/sync',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ name: session.user.user_metadata?.name ?? '' }),
      },
    );
  } catch {
    // Non-critical — the backend auto-creates on any authenticated request too
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Listen to Supabase auth state changes
  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        setUser(toAppUser(session.user));
      }
      setLoading(false);
    });

    // Subscribe to changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (session?.user) {
          setUser(toAppUser(session.user));
        } else {
          setUser(null);
        }
      },
    );

    return () => subscription.unsubscribe();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
<<<<<<< Updated upstream
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { name } },
    });
    if (error) throw new Error(error.message);
    // Sync to backend so the User row is created immediately
    if (data.session) {
      await syncUserToBackend(data.session);
    } else if (data.user && !data.session) {
      // Email confirmation is enabled in Supabase — user created but can't login yet
      throw new Error('Account created! Check your email to confirm, then sign in.');
    }
  }, []);
=======
    try {
      const res = await authApi.login(email, password);
      persist(res.token, res.user);
    } catch (error) {
      if (!authApi.isUnavailable(error)) throw error;
      persist('demo-token', email ? { ...demoUser, email } : demoUser);
    }
  }, [persist]);

  const register = useCallback(async (n: string, e: string, p: string) => {
    try {
      const res = await authApi.register(n, e, p);
      persist(res.token, res.user);
    } catch (error) {
      if (!authApi.isUnavailable(error)) throw error;
      persist('demo-token', { id: demoUser.id, name: n || demoUser.name, email: e });
    }
  }, [persist]);
>>>>>>> Stashed changes

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
