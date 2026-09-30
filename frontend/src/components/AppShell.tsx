import { useEffect, useRef, useState } from "react";
import { Bell, LogOut, Menu, ShieldCheck, X } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { navigationItems, ROLE_LABELS, type SystemRole } from "../navigation";
import { StatusBadge } from "./ui";
import { useAuth } from "../auth/AuthContext";
import { useLiveConnection } from "../live/LiveConnectionContext";

export type ShellUser = { email: string; role: SystemRole };

function SidebarContent({ onNavigate, role }: { onNavigate?: () => void; role?: SystemRole | null }) {
  const visibleItems = navigationItems.filter((item) => !role || item.allowedRoles.includes(role));
  return <>
    <div className="brand"><div className="brand-mark" aria-hidden="true"><ShieldCheck size={21} strokeWidth={2.3} /></div><div><strong>CityResponder</strong><span>Operational console</span></div></div>
    <nav className="sidebar-nav" aria-label="Primary navigation">
      <p className="nav-section-label">Main</p>
      {visibleItems.filter((item) => item.section === "main").map((item) => { const Icon = item.icon; return <NavLink key={item.path} to={item.path} end={item.activeMatch === "exact"} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`} onClick={onNavigate}><Icon size={17} aria-hidden="true" />{item.label}</NavLink>; })}
      <p className="nav-section-label system-label">System</p>
      {visibleItems.filter((item) => item.section === "system").map((item) => { const Icon = item.icon; return <NavLink key={item.path} to={item.path} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`} onClick={onNavigate}><Icon size={17} aria-hidden="true" />{item.label}</NavLink>; })}
    </nav>
  </>;
}

function SidebarFooter() {
  return <div className="sidebar-footer"><div className="sidebar-divider" /><p className="sidebar-motto">SITUATIONAL CLARITY<br />WHEN IT MATTERS</p><div className="sidebar-accent-bar" /><strong className="sidebar-footer-brand">CityResponder</strong></div>;
}

export function Sidebar({ onNavigate, role }: { onNavigate?: () => void; role?: SystemRole | null }) {
  return <aside className="sidebar" aria-label="Primary navigation"><SidebarContent onNavigate={onNavigate} role={role} /><SidebarFooter /></aside>;
}

export function Topbar({ user, onMenu, onLogout }: { user: ShellUser; onMenu: () => void; onLogout: () => void }) {
  const location = useLocation();
  const live = useLiveConnection();
  const title = navigationItems.find((item) => item.path === location.pathname)?.label ?? "CityResponder";
  const liveLabel = live.status === "connected" ? "Live updates connected" : live.status === "connecting" ? "Connecting live updates" : live.status === "error" ? "Live updates unavailable" : "Live updates offline";
  const liveTone = live.status === "connected" ? "success" : live.status === "error" ? "danger" : live.status === "connecting" ? "warning" : "neutral";
  return <header className="topbar"><div className="topbar-heading"><button className="mobile-menu-button icon-button" type="button" aria-label="Open navigation menu" onClick={onMenu}><Menu size={18} /></button><div><p className="eyebrow">Emergency response platform</p><h1>{title}</h1></div></div><div className="topbar-actions"><StatusBadge tone={liveTone}>{liveLabel}</StatusBadge><div className="role-chip"><span>{ROLE_LABELS[user.role]}</span><small>{user.email}</small></div><button className="icon-button" type="button" aria-label="Sign out" onClick={onLogout}><LogOut size={17} /></button></div></header>;
}

export function MobileNavigation({ open, onClose, role }: { open: boolean; onClose: () => void; role?: SystemRole | null }) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (open) closeButtonRef.current?.focus(); }, [open]);
  useEffect(() => { if (!open) return; const handleKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); }; document.addEventListener("keydown", handleKeyDown); return () => document.removeEventListener("keydown", handleKeyDown); }, [open, onClose]);
  if (!open) return null;
  return <><div className="mobile-sidebar-backdrop" aria-hidden="true" onClick={onClose} /><aside className="mobile-sidebar" aria-label="Mobile navigation" aria-modal="true"><div className="mobile-sidebar-header"><button ref={closeButtonRef} className="icon-button" type="button" aria-label="Close navigation menu" onClick={onClose}><X size={18} /></button></div><SidebarContent onNavigate={onClose} role={role} /><SidebarFooter /></aside></>;
}

export function AppShell({ user }: { user: ShellUser }) {
  const [open, setOpen] = useState(false);
  const { logout } = useAuth();
  return <div className="app-shell"><Sidebar role={user.role} /><MobileNavigation open={open} onClose={() => setOpen(false)} role={user.role} /><main className="main-shell"><Topbar user={user} onMenu={() => setOpen(true)} onLogout={logout} /><div className="page-grid"><Outlet /></div></main></div>;
}
