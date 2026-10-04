import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RoleHomeRedirect } from "./pages";
import { LoginPage } from "./pages/LoginPage";
import { OperatorOverviewPage } from "./pages/OperatorOverviewPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { OperatorIncidentPage } from "./pages/OperatorIncidentPage";
import { FirefighterResponsePage } from "./pages/FirefighterResponsePage";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { RequireAuth, RequireRole } from "./auth/guards";
import { navigationItems } from "./navigation";
import { LiveConnectionProvider } from "./live/LiveConnectionContext";
import { RiskPlannerPage } from "./pages/RiskPlannerPage";
import { AdminCalibrationPage } from "./pages/AdminCalibrationPage";
import { HistoryAuditPage } from "./pages/HistoryAuditPage";
import { PublicShowcaseApp } from "./pages/PublicShowcaseApp";

function ProtectedShell() {
  const { user } = useAuth();
  if (!user) return null;
  return <AppShell user={user} />;
}

export default function App() {
  if (import.meta.env.VITE_PUBLIC_SHOWCASE === "true") return <PublicShowcaseApp />;
  const routeRoles = (path: string) => navigationItems.find((item) => item.path === path)?.allowedRoles ?? [];
  return <AuthProvider><LiveConnectionProvider><BrowserRouter><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<RequireAuth><ProtectedShell /></RequireAuth>}>
      <Route index element={<RoleLanding />} />
      <Route path="incidents" element={<RequireRole allowedRoles={routeRoles("/incidents")}><IncidentsPage /></RequireRole>} />
      <Route path="incidents/:decisionId" element={<RequireRole allowedRoles={routeRoles("/incidents")}><OperatorIncidentPage /></RequireRole>} />
      <Route path="response" element={<RequireRole allowedRoles={routeRoles("/response")}><FirefighterResponsePage /></RequireRole>} />
      <Route path="risk" element={<RequireRole allowedRoles={routeRoles("/risk")}><RiskPlannerPage /></RequireRole>} />
      <Route path="history" element={<RequireRole allowedRoles={routeRoles("/history")}><HistoryAuditPage /></RequireRole>} />
      <Route path="admin" element={<RequireRole allowedRoles={routeRoles("/admin")}><AdminCalibrationPage /></RequireRole>} />
    </Route>
  </Routes></BrowserRouter></LiveConnectionProvider></AuthProvider>;
}

function RoleLanding() { const { role } = useAuth(); return role === "OPERATOR" || role === "ADMIN" ? <OperatorOverviewPage /> : role ? <RoleHomeRedirect role={role} /> : null; }
