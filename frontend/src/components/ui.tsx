import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { Archive, AlertCircle, LoaderCircle } from "lucide-react";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

function cx(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

export function Button({ className, variant = "primary", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  return <button className={cx("button", `button-${variant}`, className)} {...props} />;
}

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cx("card", className)} {...props} />;
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("badge", `badge-${tone}`)}>{children}</span>;
}

export function StatusBadge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("status-badge", `status-${tone}`)}><span className="status-dot" aria-hidden="true" />{children}</span>;
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="page-header"><div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>{action ? <div className="page-header-action">{action}</div> : null}</div>;
}

export function SectionHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="section-header"><div><h3>{title}</h3>{description ? <p>{description}</p> : null}</div>{action}</div>;
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <div className="state-panel" role="status"><LoaderCircle className="spin" size={20} aria-hidden="true" /><span>{label}</span></div>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="state-panel empty-state"><Archive size={22} aria-hidden="true" /><h3>{title}</h3><p>{body}</p></div>;
}

export function ErrorState({ title = "Unable to load", body }: { title?: string; body: string }) {
  return <div className="state-panel error-state" role="alert"><AlertCircle size={22} aria-hidden="true" /><h3>{title}</h3><p>{body}</p></div>;
}
