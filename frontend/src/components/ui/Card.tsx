import type { ReactNode } from "react";
import clsx from "clsx";

export function Card({ children, className, padded = true }: { children: ReactNode; className?: string; padded?: boolean }) {
  return <div className={clsx("card", padded && "p-5", className)}>{children}</div>;
}

export function CardHeader({ title, description, actions, className }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={clsx("mb-4 flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-stone-900">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-stone-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "bad" | "warn" }) {
  const tones = { default: "text-stone-900", good: "text-green-800", bad: "text-red-700", warn: "text-amber-800" };
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium text-stone-500">{label}</div>
      <div className={clsx("num mt-1 truncate text-lg font-semibold", tones[tone || "default"])}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-stone-500">{hint}</div>}
    </div>
  );
}

export function DefinitionList({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-xs font-medium text-stone-500">{k}</dt>
          <dd className="mt-0.5 text-sm text-stone-900">{v || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
