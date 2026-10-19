import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, type Me } from "./api";

interface AuthCtx { me: Me | null; loading: boolean; refresh: () => Promise<void>; signIn: (token: string) => Promise<void>; signOut: () => void }
const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(!!getToken());

  const refresh = useCallback(async () => {
    if (!getToken()) { setMe(null); setLoading(false); return; }
    try { setMe(await api.me()); } catch { setMe(null); } finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const off = () => setMe(null);
    window.addEventListener("jobagent:signed-out", off);
    return () => window.removeEventListener("jobagent:signed-out", off);
  }, []);

  const signIn = async (token: string) => { setToken(token); setLoading(true); await refresh(); };
  const signOut = () => { setToken(null); setMe(null); };
  return <Ctx.Provider value={{ me, loading, refresh, signIn, signOut }}>{children}</Ctx.Provider>;
}
