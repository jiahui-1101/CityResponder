import { useCallback, useEffect, useState } from "react";
import { adminUserRequests, type AdminRole, type AdminUser } from "../api/adminUsers";

export function useAdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setError(null);
    try { setUsers(await adminUserRequests.list()); setLastRefreshedAt(new Date().toISOString()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load users"); }
    finally { setLoading(false); }
  }, []);
  const create = useCallback((email: string, password: string, role: AdminRole) => adminUserRequests.create(email, password, role), []);
  const update = useCallback((id: number, values: Partial<Pick<AdminUser, "role" | "is_active">>) => adminUserRequests.update(id, values), []);
  useEffect(() => { void refresh(); }, [refresh]);
  return { users, loading, error, lastRefreshedAt, refresh, create, update };
}
