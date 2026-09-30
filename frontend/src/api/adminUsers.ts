import { apiRequest } from "./client";

export type AdminRole = "OPERATOR" | "FIREFIGHTER" | "RISK_PLANNER" | "ADMIN";
export type AdminUser = { id: number; email: string; role: AdminRole; is_active: boolean; created_at: string };
export const ADMIN_ROLES: AdminRole[] = ["OPERATOR", "FIREFIGHTER", "RISK_PLANNER", "ADMIN"];

export const adminUserRequests = {
  list: () => apiRequest<AdminUser[]>("/api/admin/users"),
  create: (email: string, password: string, role: AdminRole) => apiRequest<AdminUser>("/api/admin/users", { method: "POST", body: JSON.stringify({ email, password, role }) }),
  update: (userId: number, update: Partial<Pick<AdminUser, "role" | "is_active">>) => apiRequest<AdminUser>(`/api/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(update) }),
};
