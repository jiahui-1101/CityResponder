import { Check, KeyRound, RefreshCw, ShieldAlert, UserPlus, UserRound, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { ADMIN_ROLES, type AdminRole, type AdminUser } from "../api/adminUsers";
import { Card, EmptyState, ErrorState, LoadingState, SectionHeader, StatusBadge } from "../components/ui";
import { useAdminUsers } from "../hooks/useAdminUsers";
import { useAuth } from "../auth/AuthContext";

const formatTime = (value: string) => new Date(value).toLocaleString();
const roleTone = (role: AdminRole): "info" | "neutral" | "warning" | "success" => role === "ADMIN" ? "warning" : role === "RISK_PLANNER" ? "info" : role === "FIREFIGHTER" ? "success" : "neutral";

export function AdminUsersPanel() {
  const state = useAdminUsers();
  const { user: currentUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AdminRole>("OPERATOR");
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ kind: "create" | "role" | "active"; user?: AdminUser; nextRole?: AdminRole; nextActive?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitCreate(event?: FormEvent) {
    event?.preventDefault();
    if (!email.trim() || !password) { setFormError("Email and password are required."); return; }
    setFormError(null);
    if (role === "ADMIN") { setPending({ kind: "create" }); return; }
    await createUser();
  }
  async function createUser() {
    setBusy(true); setActionError(null);
    try { await state.create(email, password, role); setEmail(""); setPassword(""); setRole("OPERATOR"); setPending(null); await state.refresh(); }
    catch (caught) { setPassword(""); setActionError(caught instanceof ApiError ? `${caught.status}: ${caught.message}` : "Unable to create user"); }
    finally { setBusy(false); }
  }
  async function confirmAction() {
    if (!pending) return;
    if (pending.kind === "create") { await createUser(); return; }
    if (!pending.user) return;
    setBusy(true); setActionError(null);
    try { await state.update(pending.user.id, pending.kind === "role" ? { role: pending.nextRole } : { is_active: pending.nextActive }); setPending(null); await state.refresh(); }
    catch (caught) { setActionError(caught instanceof ApiError ? `${caught.status}: ${caught.message}` : "Unable to update user"); }
    finally { setBusy(false); }
  }
  function requestRoleChange(target: AdminUser, nextRole: AdminRole) { if (target.id === currentUser?.id) { setActionError("For safety, this page does not allow changing your own role."); return; } setPending({ kind: "role", user: target, nextRole }); }
  function requestActivation(target: AdminUser) { if (target.id === currentUser?.id && target.is_active) { setActionError("For safety, this page does not allow deactivating your own account."); return; } setPending({ kind: "active", user: target, nextActive: !target.is_active }); }

  if (state.loading && !state.users.length) return <LoadingState label="Loading users" />;
  return <div className="admin-users-panel"><div className="page-header"><div><p className="eyebrow">System Administrator</p><h2>Users & access</h2><p>Manage local accounts and their four source-backed roles. Changes are server-authorized.</p></div><div className="overview-refresh"><span>{state.lastRefreshedAt ? `Updated ${formatTime(state.lastRefreshedAt)}` : "Not refreshed yet"}</span><button className="button button-secondary" type="button" onClick={() => void state.refresh()} disabled={state.loading}><RefreshCw size={15} className={state.loading ? "spin" : undefined} />{state.loading ? "Refreshing" : "Refresh"}</button></div></div>
    {state.error ? <ErrorState body={state.error} /> : null}{actionError ? <div className="section-error" role="alert"><ShieldAlert size={15} />{actionError}</div> : null}
    <section className="overview-section"><SectionHeader title="Create user" description="Passwords are sent only to the existing create-user endpoint and are never displayed or stored here." /><Card className="admin-create-card"><form className="admin-create-form" onSubmit={submitCreate}><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="off" required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as AdminRole)}>{ADMIN_ROLES.map((item) => <option value={item} key={item}>{item}</option>)}</select></label><button className="button button-primary" type="submit" disabled={busy}><UserPlus size={15} />Create user</button></form>{formError ? <p className="form-error" role="alert">{formError}</p> : null}</Card></section>
    <section className="overview-section"><SectionHeader title="Local users" description="Inactive accounts are retained, not deleted." />{state.users.length === 0 ? <Card><EmptyState title="No users returned" body="The backend returned no local user accounts." /></Card> : <Card className="admin-users-card"><div className="admin-users-head"><span>ID</span><span>Email</span><span>Role</span><span>State</span><span>Created</span><span>Actions</span></div>{state.users.map((item) => <UserRow key={item.id} user={item} currentUserId={currentUser?.id} onRole={(next) => requestRoleChange(item, next)} onToggle={() => requestActivation(item)} />)}</Card>}</section>
    <section className="overview-section"><SectionHeader title="Access roles" description="Application access mapping from the centralized navigation policy; permissions are not editable here." /><Card className="access-role-grid">{ADMIN_ROLES.map((item) => <div key={item} className="access-role-item"><StatusBadge tone={roleTone(item)}>{item}</StatusBadge><span>{item === "OPERATOR" ? "Operational overview, incidents, response, and audit." : item === "FIREFIGHTER" ? "Response/routing, incidents, and audit." : item === "RISK_PLANNER" ? "Risk intelligence and audit." : "Administrative governance and all current protected areas."}</span></div>)}</Card></section>
    {pending ? <div className="modal-backdrop" role="presentation"><div className="decision-modal" role="dialog" aria-modal="true" aria-labelledby="user-confirm-title"><div className="modal-heading"><div><p className="eyebrow">Access change</p><h3 id="user-confirm-title">Confirm {pending.kind === "create" ? "user creation" : pending.kind === "role" ? "role change" : pending.nextActive ? "activation" : "deactivation"}</h3></div><button className="icon-button" type="button" aria-label="Close confirmation" onClick={() => setPending(null)}><X size={17} /></button></div><p className="modal-context">{pending.kind === "create" ? `Create ${email} as ${role}?` : pending.kind === "role" ? `Change ${pending.user?.email} from ${pending.user?.role} to ${pending.nextRole}?` : `${pending.nextActive ? "Activate" : "Deactivate"} ${pending.user?.email}? Deactivation disables authentication; it does not delete the account.`}</p><div className="modal-actions"><button className="button button-quiet" type="button" onClick={() => setPending(null)}>Cancel</button><button className="button button-primary" type="button" onClick={() => void confirmAction()} disabled={busy}>{busy ? "Applying…" : "Confirm"}</button></div></div></div> : null}
  </div>;
}

function UserRow({ user, currentUserId, onRole, onToggle }: { user: AdminUser; currentUserId?: number; onRole: (role: AdminRole) => void; onToggle: () => void }) { return <div className="admin-user-row"><span>{user.id}</span><div className="admin-user-identity"><UserRound size={15} /><strong>{user.email}</strong></div><select value={user.role} disabled={user.id === currentUserId} aria-label={`Role for ${user.email}`} onChange={(event) => onRole(event.target.value as AdminRole)}>{ADMIN_ROLES.map((item) => <option value={item} key={item}>{item}</option>)}</select><StatusBadge tone={user.is_active ? "success" : "neutral"}>{user.is_active ? "Active" : "Inactive"}</StatusBadge><time>{formatTime(user.created_at)}</time><div className="admin-user-actions"><button className="button button-quiet" type="button" onClick={onToggle} disabled={user.id === currentUserId && user.is_active}>{user.is_active ? "Deactivate" : "Activate"}</button></div></div>; }
