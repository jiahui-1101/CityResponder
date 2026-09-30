import { AlertCircle } from "lucide-react";
import { Navigate } from "react-router-dom";
import { ROLE_HOME_ROUTES, type SystemRole } from "./navigation";

export function AccessDeniedPage() {
  return <div className="access-denied"><AlertCircle size={24} aria-hidden="true" /><h2>Access denied</h2><p>Your current role does not have access to this CityResponder area.</p></div>;
}

export function RoleHomeRedirect({ role }: { role: SystemRole }) {
  const destination = ROLE_HOME_ROUTES[role];
  return destination ? <Navigate to={destination} replace /> : <AccessDeniedPage />;
}
