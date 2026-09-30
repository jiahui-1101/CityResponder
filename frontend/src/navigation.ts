import {
  Activity,
  BookOpen,
  Building2,
  ClipboardList,
  LayoutDashboard,
  Route,
  type LucideIcon,
} from "lucide-react";

export type SystemRole = "OPERATOR" | "FIREFIGHTER" | "RISK_PLANNER" | "ADMIN";

export type NavigationItem = {
  label: string;
  path: string;
  icon: LucideIcon;
  allowedRoles: SystemRole[];
  activeMatch: "exact" | "section";
  section: "main" | "system";
};

const operationalRoles: SystemRole[] = ["OPERATOR", "FIREFIGHTER", "ADMIN"];
const riskRoles: SystemRole[] = ["RISK_PLANNER", "ADMIN"];
const historyRoles: SystemRole[] = ["OPERATOR", "FIREFIGHTER", "RISK_PLANNER", "ADMIN"];

// Visibility metadata only; Step 3 will connect real authentication and RBAC.
export const navigationItems: NavigationItem[] = [
  { label: "Overview", path: "/", icon: LayoutDashboard, allowedRoles: historyRoles, activeMatch: "exact", section: "main" },
  { label: "Incidents", path: "/incidents", icon: Activity, allowedRoles: operationalRoles, activeMatch: "section", section: "main" },
  { label: "Response / Routing", path: "/response", icon: Route, allowedRoles: operationalRoles, activeMatch: "section", section: "main" },
  { label: "Risk Intelligence", path: "/risk", icon: Building2, allowedRoles: riskRoles, activeMatch: "section", section: "main" },
  { label: "History / Audit", path: "/history", icon: BookOpen, allowedRoles: historyRoles, activeMatch: "section", section: "main" },
  { label: "Administration", path: "/admin", icon: ClipboardList, allowedRoles: ["ADMIN"], activeMatch: "section", section: "system" },
];

export const ROLE_HOME_ROUTES: Record<SystemRole, string> = {
  OPERATOR: "/",
  FIREFIGHTER: "/response",
  RISK_PLANNER: "/risk",
  ADMIN: "/admin",
};
