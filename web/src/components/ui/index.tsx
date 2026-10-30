import clsx from "clsx";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

export { clsx as cx };

type Tone = "neutral" | "brand" | "accent" | "danger" | "info";

const toneClass: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  brand: "bg-brand-soft text-brand-strong",
  accent: "bg-accent-soft text-accent",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        toneClass[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
const buttonVariant = {
  primary: "bg-brand text-white hover:bg-brand-strong",
  secondary: "border border-border bg-surface text-text hover:bg-surface-2",
  ghost: "text-muted hover:bg-surface-2 hover:text-text",
  danger: "bg-danger text-white hover:opacity-90",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ComponentProps<"button"> & { variant?: keyof typeof buttonVariant }) {
  return <button className={clsx(buttonBase, buttonVariant[variant], className)} {...props} />;
}

export function ButtonLink({
  variant = "primary",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: keyof typeof buttonVariant }) {
  return <Link className={clsx(buttonBase, buttonVariant[variant], className)} {...props} />;
}

export function Card({ className, children, ...props }: ComponentProps<"div">) {
  return (
    <div className={clsx("rounded-xl border border-border bg-surface", className)} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ title, description, action }: { title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  crumbs,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  crumbs?: { href: string; label: string }[];
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {crumbs && (
          <nav className="mb-1 flex flex-wrap items-center gap-1 text-xs text-muted">
            {crumbs.map((c) => (
              <span key={c.href} className="flex items-center gap-1">
                <Link href={c.href} className="hover:text-text">
                  {c.label}
                </Link>
                <span aria-hidden>/</span>
              </span>
            ))}
          </nav>
        )}
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={clsx("tabular mt-1 text-2xl font-semibold", tone === "brand" && "text-brand")}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="text-sm font-semibold">{title}</div>
      {body && <p className="max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("overflow-x-auto", className)}>
      <table className="w-full min-w-[640px] text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <th className={clsx("border-b border-border px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted", className)}>
      {children}
    </th>
  );
}

export function Td({ children, className, ...props }: ComponentProps<"td">) {
  return (
    <td className={clsx("border-b border-border px-4 py-3 align-top", className)} {...props}>
      {children}
    </td>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={clsx("flex flex-col gap-1.5 text-sm", className)}>
      <span className="font-medium">{label}</span>
      {children}
      {error ? <span className="text-xs text-danger">{error}</span> : hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-[var(--ring)]";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={clsx(inputClass, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={clsx(inputClass, "font-mono", className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={clsx(inputClass, "pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: Tone; title?: ReactNode; children: ReactNode }) {
  return (
    <div className={clsx("rounded-lg px-4 py-3 text-sm", toneClass[tone])}>
      {title && <div className="mb-0.5 font-semibold">{title}</div>}
      <div className="text-text/90">{children}</div>
    </div>
  );
}

/** A file download. Plain <a>, so the browser saves it instead of routing. */
export function DownloadLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} className={clsx(buttonBase, buttonVariant.secondary)}>
      {children}
    </a>
  );
}
