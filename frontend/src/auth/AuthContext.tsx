import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, ACCESS_TOKEN_KEY, currentUserRequest, loginRequest, type CurrentUser } from "../api/client";
import { type SystemRole } from "../navigation";

type AuthContextValue = {
  user: CurrentUser | null;
  role: CurrentUser["role"] | null;
  authenticated: boolean;
  initializing: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<CurrentUser>;
  logout: () => void;
  refreshCurrentUser: () => Promise<CurrentUser | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const isSystemRole = (role: unknown): role is SystemRole => ["OPERATOR", "FIREFIGHTER", "RISK_PLANNER", "ADMIN"].includes(String(role));

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const logout = useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    setUser(null);
    setError(null);
  }, []);

  const refreshCurrentUser = useCallback(async () => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (!token) { setUser(null); return null; }
    try {
      const current = await currentUserRequest(token);
      if (!isSystemRole(current.role) || !current.is_active) { logout(); setError("This account is not authorized to use CityResponder."); return null; }
      setUser(current);
      setError(null);
      return current;
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) logout();
      else setError(caught instanceof Error ? caught.message : "Unable to load current user");
      return null;
    }
  }, [logout]);

  useEffect(() => { void refreshCurrentUser().finally(() => setInitializing(false)); }, [refreshCurrentUser]);
  useEffect(() => { const handleUnauthorized = () => logout(); window.addEventListener("cityresponder:unauthorized", handleUnauthorized); return () => window.removeEventListener("cityresponder:unauthorized", handleUnauthorized); }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    const response = await loginRequest(email, password);
    // Prototype strategy: keep only the short-lived JWT in localStorage; no credentials are stored.
    localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token);
    try { const current = await refreshCurrentUser(); if (!current) throw new Error("Unable to establish the authenticated session"); return current; }
    catch (caught) { logout(); throw caught; }
  }, [logout, refreshCurrentUser]);

  const value = useMemo(() => ({ user, role: user?.role ?? null, authenticated: user !== null, initializing, error, login, logout, refreshCurrentUser }), [error, initializing, login, logout, refreshCurrentUser, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
