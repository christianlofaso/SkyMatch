"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase, authConfigured, authRequired } from "@/lib/supabase";
import { TurnstileWidget } from "@/components/TurnstileWidget";

interface AuthState {
  session: Session | null;
  user: User | null;
  loading: boolean;          // true until the initial getSession() resolves
  authConfigured: boolean;   // sign-in available at all
  authRequired: boolean;     // gates enforce (NEXT_PUBLIC_AUTH_REQUIRED)
  signInWithOtp: (email: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
}

// Safe anonymous default so useAuth() never throws if a component renders outside the
// provider (e.g. an isolated test) or when auth is unconfigured.
const DEFAULT: AuthState = {
  session: null,
  user: null,
  loading: false,
  authConfigured: false,
  authRequired: false,
  signInWithOtp: async () => ({ error: "Auth is not configured." }),
  signOut: async () => {},
};

const AuthContext = createContext<AuthState>(DEFAULT);

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const configured = authConfigured();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState<boolean>(configured);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session);
        setLoading(false);
      }
    });
    // Fires on sign-in (incl. magic-link return via detectSessionInUrl), refresh, sign-out.
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });
    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value: AuthState = {
    session,
    user: session?.user ?? null,
    loading,
    authConfigured: configured,
    authRequired: authRequired(),
    signInWithOtp: async (email: string) => {
      if (!supabase) return { error: "Auth is not configured." };
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: {
          // Return the user to the page they were on so the gate flips live in place.
          emailRedirectTo: typeof window !== "undefined" ? window.location.href : undefined,
        },
      });
      return { error: error?.message ?? null };
    },
    signOut: async () => {
      await supabase?.auth.signOut();
    },
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
      {/* Invisible Turnstile widget (no-ops without a site key) — feeds gated API requests. */}
      <TurnstileWidget />
    </AuthContext.Provider>
  );
}
