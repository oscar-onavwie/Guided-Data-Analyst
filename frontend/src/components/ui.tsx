// Small, accessible building blocks shared across the app.

import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function Card({ title, description, actions, children, className }: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-xl border border-zinc-200 bg-white p-4 shadow-sm sm:p-5", className)}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-base font-semibold text-zinc-900">{title}</h2>}
            {description && <p className="mt-1 text-sm text-zinc-600">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-teal-700 text-white hover:bg-teal-800 disabled:bg-zinc-300 disabled:text-zinc-600",
  secondary: "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50 disabled:text-zinc-400",
  ghost: "text-zinc-700 hover:bg-zinc-100 disabled:text-zinc-400",
  danger: "border border-red-200 bg-white text-red-700 hover:bg-red-50 disabled:text-zinc-400",
};

export function Button({ variant = "primary", className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
}) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed",
        BUTTON_STYLES[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function LinkButton({ variant = "secondary", className, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: ButtonVariant;
}) {
  return (
    <a
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors",
        BUTTON_STYLES[variant],
        className,
      )}
      {...props}
    >
      {children}
    </a>
  );
}

type Tone = "neutral" | "teal" | "amber" | "red" | "indigo" | "violet";

const BADGE_STYLES: Record<Tone, string> = {
  neutral: "bg-zinc-100 text-zinc-700",
  teal: "bg-teal-50 text-teal-800 ring-1 ring-teal-200",
  amber: "bg-amber-50 text-amber-900 ring-1 ring-amber-200",
  red: "bg-red-50 text-red-800 ring-1 ring-red-200",
  indigo: "bg-indigo-50 text-indigo-800 ring-1 ring-indigo-200",
  violet: "bg-violet-50 text-violet-800 ring-1 ring-violet-200",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold", BADGE_STYLES[tone], className)}>
      {children}
    </span>
  );
}

export function Alert({ tone = "info", title, children }: { tone?: "info" | "error" | "warning" | "success"; title?: ReactNode; children: ReactNode }) {
  const styles = {
    info: "border-sky-200 bg-sky-50 text-sky-900",
    error: "border-red-200 bg-red-50 text-red-900",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
    success: "border-teal-200 bg-teal-50 text-teal-900",
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("rounded-lg border px-4 py-3 text-sm", styles)}>
      {title && <p className="font-semibold">{title}</p>}
      <div className={title ? "mt-1" : undefined}>{children}</div>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-zinc-600" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-teal-700" aria-hidden="true" />
      {label}
    </span>
  );
}

export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center rounded-xl border border-dashed border-zinc-300 bg-white p-8">
      <Spinner label={label} />
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 bg-white p-8 text-center">
      <p className="font-medium text-zinc-800">{title}</p>
      {children && <div className="mt-2 text-sm text-zinc-600">{children}</div>}
    </div>
  );
}

export function Kpi({ label, value, hint, tone = "neutral" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "neutral" | "warn" | "bad" }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p
        className={cx(
          "mt-1 text-2xl font-semibold tabular-nums",
          tone === "neutral" && "text-zinc-900",
          tone === "warn" && "text-amber-700",
          tone === "bad" && "text-red-700",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

export function Select({ label, value, onChange, options, id, disabled }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  id: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-zinc-600">
        {label}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-40 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 disabled:bg-zinc-100"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, active, onChange, label }: {
  tabs: { id: T; label: string; disabled?: boolean }[];
  active: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-zinc-200">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={active === t.id}
          aria-controls={`panel-${t.id}`}
          disabled={t.disabled}
          onClick={() => onChange(t.id)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:text-zinc-400",
            active === t.id ? "border-teal-700 text-teal-800" : "border-transparent text-zinc-600 hover:text-zinc-900",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function StatList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-4">
      {items.map((i) => (
        <div key={i.label} className="flex flex-col">
          <dt className="text-xs text-zinc-500">{i.label}</dt>
          <dd className="font-medium tabular-nums text-zinc-900">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}
