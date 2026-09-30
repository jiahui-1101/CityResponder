import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingState } from "../components/ui";
import { AccessDeniedPage } from "../pages";
import { type SystemRole } from "../navigation";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { authenticated, initializing, error } = useAuth();
  const location = useLocation();
  if (initializing) return <LoadingState label="Restoring secure session" />;
  if (!authenticated && error) return <AccessDeniedPage />;
  if (!authenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

export function RequireRole({ allowedRoles, children }: { allowedRoles: SystemRole[]; children: ReactNode }) {
  const { role, initializing } = useAuth();
  if (initializing) return <LoadingState label="Checking access" />;
  if (!role) return <Navigate to="/login" replace />;
  return allowedRoles.includes(role) ? <>{children}</> : <AccessDeniedPage />;
}
