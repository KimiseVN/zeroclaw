"use client";
import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// Turnstile context
//
// token === null    → verification not yet complete (waiting)
// token === string  → verified (real user) or bypass (fail-open on error/timeout)
// verified          → true when token is available
// ─────────────────────────────────────────────────────────────────────────────

type TurnstileCtx = {
  token:    string | null;
  setToken: (t: string | null) => void;
  verified: boolean;
};

const Ctx = createContext<TurnstileCtx>({
  token:    null,
  setToken: () => {},
  verified: false,
});

export function TurnstileProvider({ children }: { children: ReactNode }) {
  const [token, rawSet] = useState<string | null>(null);
  const setToken = useCallback((t: string | null) => rawSet(t), []);

  return (
    <Ctx.Provider value={{ token, setToken, verified: token !== null }}>
      {children}
    </Ctx.Provider>
  );
}

export const useTurnstile = () => useContext(Ctx);
