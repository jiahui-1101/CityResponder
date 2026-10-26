import {
  Check,
  KeyRound,
  RefreshCw,
  ShieldAlert,
  UserPlus,
  UserRound,
  X,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { ADMIN_ROLES, type AdminRole, type AdminUser } from "../api/adminUsers";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionHeader,
  StatusBadge,
} from "../components/ui";
import { useAdminUsers } from "../hooks/useAdminUsers";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../navigation";
import { useEscapeDismiss } from "../hooks/useEscapeDismiss";
import { formatWhen } from "../copy/glossary";

const roleTone = (
  role: AdminRole
): "info" | "neutral" | "warning" | "success" =>
  role === "ADMIN"
    ? "warning"
    : role === "RISK_PLANNER"
      ? "info"
      : role === "FIREFIGHTER"
        ? "success"
        : "neutral";

export function AdminUsersPanel() {
  const state = useAdminUsers();
  const { user: currentUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AdminRole>("OPERATOR");
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState<{
    kind: "create" | "role" | "active";
    user?: AdminUser;
    nextRole?: AdminRole;
    nextActive?: boolean;
  } | null>(null);
  useEscapeDismiss(pending !== null, () => setPending(null));
  const [busy, setBusy] = useState(false);

  async function submitCreate(event?: FormEvent) {
    event?.preventDefault();
    if (!email.trim() || !password) {
      setFormError("Email and password are required.");
      return;
    }
    setFormError(null);
    if (role === "ADMIN") {
      setPending({ kind: "create" });
      return;
    }
    await createUser();
  }

  async function createUser() {
    setBusy(true);
    setActionError(null);
    try {
      await state.create(email, password, role);
      setEmail("");
      setPassword("");
      setRole("OPERATOR");
      setPending(null);
      await state.refresh();
    } catch (caught) {
      setPassword("");
      setActionError(
        caught instanceof ApiError
          ? `${caught.status}: ${caught.message}`
          : "Unable to create user"
      );
    } finally {
      setBusy(false);
    }
  }

  async function confirmAction() {
    if (!pending) return;
    if (pending.kind === "create") {
      await createUser();
      return;
    }
    if (!pending.user) return;
    setBusy(true);
    setActionError(null);
    try {
      await state.update(
        pending.user.id,
        pending.kind === "role"
          ? { role: pending.nextRole }
          : { is_active: pending.nextActive }
      );
      setPending(null);
      await state.refresh();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? `${caught.status}: ${caught.message}`
          : "Unable to update user"
      );
    } finally {
      setBusy(false);
    }
  }

  function requestRoleChange(target: AdminUser, nextRole: AdminRole) {
    if (target.id === currentUser?.id) {
      setActionError("For safety, this page does not allow changing your own role.");
      return;
    }
    setPending({ kind: "role", user: target, nextRole });
  }

  function requestActivation(target: AdminUser) {
    if (target.id === currentUser?.id && target.is_active) {
      setActionError("For safety, this page does not allow deactivating your own account.");
      return;
    }
    setPending({ kind: "active", user: target, nextActive: !target.is_active });
  }

  if (state.loading && !state.users.length)
    return <LoadingState label="Loading users" />;

  return (
    <div className="admin-users-panel">
      <div className="page-header">
        <div>
          <p className="eyebrow">System Administrator</p>
          <h2>Users &amp; access</h2>
          <p>
            Manage local accounts and their system roles. Access changes are
            server-authorized.
          </p>
        </div>
        <div className="overview-refresh">
          <span>
            {state.lastRefreshedAt
              ? `Updated ${formatWhen(state.lastRefreshedAt)}`
              : "Not refreshed yet"}
          </span>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => void state.refresh()}
            disabled={state.loading}
            title="Refresh user accounts list"
          >
            <RefreshCw
              size={15}
              className={state.loading ? "spin" : undefined}
            />
            {state.loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      {state.error ? <ErrorState body={state.error} /> : null}
      {actionError ? (
        <div className="section-error" role="alert">
          <ShieldAlert size={15} />
          {actionError}
        </div>
      ) : null}

      <section className="overview-section">
        <SectionHeader
          title="Create user account"
          description="Passwords are sent securely to the server and are never stored or displayed in the browser."
        />
        <Card className="admin-create-card">
          <form className="admin-create-form" onSubmit={submitCreate}>
            <label>
              Email address
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="off"
                placeholder="name@example.com"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                placeholder="Enter password"
                required
              />
            </label>
            <label>
              Role
              <select
                value={role}
                onChange={(event) => setRole(event.target.value as AdminRole)}
              >
                {ADMIN_ROLES.map((item) => (
                  <option value={item} key={item}>
                    {ROLE_LABELS[item]}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button button-primary"
              type="submit"
              disabled={busy}
              title="Create new user account"
            >
              <UserPlus size={15} />
              Create user
            </button>
          </form>
          {formError ? (
            <p className="form-error" role="alert">
              {formError}
            </p>
          ) : null}
        </Card>
      </section>

      <section className="overview-section">
        <SectionHeader
          title="User accounts"
          description="Inactive accounts are retained for audit records and cannot log in."
        />
        {state.users.length === 0 ? (
          <Card>
            <EmptyState
              title="No users returned"
              body="No user accounts were found in the database."
            />
          </Card>
        ) : (
          <Card className="admin-users-card">
            <div className="admin-users-head">
              <span>ID</span>
              <span>Email</span>
              <span>Role</span>
              <span>Status</span>
              <span>Created</span>
              <span>Actions</span>
            </div>
            {state.users.map((item) => (
              <UserRow
                key={item.id}
                user={item}
                currentUserId={currentUser?.id}
                onRole={(next) => requestRoleChange(item, next)}
                onToggle={() => requestActivation(item)}
              />
            ))}
          </Card>
        )}
      </section>

      <section className="overview-section">
        <SectionHeader
          title="Access roles"
          description="Permissions are determined by the application role policy."
        />
        <Card className="access-role-grid">
          {ADMIN_ROLES.map((item) => (
            <div key={item} className="access-role-item">
              <StatusBadge tone={roleTone(item)}>
                {ROLE_LABELS[item]}
              </StatusBadge>
              <span>
                {item === "OPERATOR"
                  ? "Operational overview, incidents, emergency response, and audit log."
                  : item === "FIREFIGHTER"
                    ? "Field route guidance, incident updates, and response audit log."
                    : item === "RISK_PLANNER"
                      ? "Area risk intelligence, inspection queue, and audit log."
                      : "Administrative governance, user management, and live diagnostics."}
              </span>
            </div>
          ))}
        </Card>
      </section>

      {pending ? (
        <div className="modal-backdrop" role="presentation">
          <div
            className="decision-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-confirm-title"
          >
            <div className="modal-heading">
              <div>
                <p className="eyebrow">Access change confirmation</p>
                <h3 id="user-confirm-title">
                  {pending.kind === "create"
                    ? "Confirm user creation"
                    : pending.kind === "role"
                      ? "Confirm role change"
                      : pending.nextActive
                        ? "Confirm activation"
                        : "Confirm deactivation"}
                </h3>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="Close confirmation"
                onClick={() => setPending(null)}
              >
                <X size={17} />
              </button>
            </div>
            <p className="modal-context">
              {pending.kind === "create"
                ? `Create account for ${email} with role "${ROLE_LABELS[role]}"?`
                : pending.kind === "role"
                  ? `Change ${pending.user?.email} role from "${
                      pending.user ? ROLE_LABELS[pending.user.role] : ""
                    }" to "${
                      pending.nextRole ? ROLE_LABELS[pending.nextRole] : ""
                    }"?`
                  : `${pending.nextActive ? "Activate" : "Deactivate"} ${
                      pending.user?.email
                    }? Deactivation prevents sign-in without deleting the account.`}
            </p>
            <div className="modal-actions">
              <button
                className="button button-quiet"
                type="button"
                onClick={() => setPending(null)}
              >
                Cancel
              </button>
              <button
                className="button button-primary"
                type="button"
                onClick={() => void confirmAction()}
                disabled={busy}
              >
                {busy ? "Applying…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function UserRow({
  user,
  currentUserId,
  onRole,
  onToggle,
}: {
  user: AdminUser;
  currentUserId?: number;
  onRole: (role: AdminRole) => void;
  onToggle: () => void;
}) {
  return (
    <div className="admin-user-row">
      <span>{user.id}</span>
      <div className="admin-user-identity">
        <UserRound size={15} />
        <strong>{user.email}</strong>
      </div>
      <select
        value={user.role}
        disabled={user.id === currentUserId}
        aria-label={`Role for ${user.email}`}
        onChange={(event) => onRole(event.target.value as AdminRole)}
      >
        {ADMIN_ROLES.map((item) => (
          <option value={item} key={item}>
            {ROLE_LABELS[item]}
          </option>
        ))}
      </select>
      <StatusBadge tone={user.is_active ? "success" : "neutral"}>
        {user.is_active ? "Active" : "Inactive"}
      </StatusBadge>
      <time dateTime={user.created_at}>{formatWhen(user.created_at)}</time>
      <div className="admin-user-actions">
        <button
          className="button button-quiet"
          type="button"
          onClick={onToggle}
          disabled={user.id === currentUserId && user.is_active}
          title={
            user.id === currentUserId && user.is_active
              ? "You cannot deactivate your own account"
              : user.is_active
                ? `Deactivate account for ${user.email}`
                : `Activate account for ${user.email}`
          }
        >
          {user.is_active ? "Deactivate" : "Activate"}
        </button>
      </div>
    </div>
  );
}
