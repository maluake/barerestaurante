import type { ReactNode } from "react";
import clsx from "clsx";
import { AlertCircle, Inbox, Loader2 } from "lucide-react";
import { Button } from "./Button";

export function Spinner({ className, label = "Carregando" }: { className?: string; label?: string }) {
  return (
    <div className={clsx("flex items-center justify-center gap-2 py-10 text-sm text-stone-500", className)} role="status">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-stone-200/70", className)} aria-hidden />;
}

export function EmptyState({ icon, title, description, action, compact }: {
  icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode; compact?: boolean;
}) {
  return (
    <div className={clsx("flex flex-col items-center justify-center text-center", compact ? "py-8" : "py-14")}>
      <div className="mb-3 rounded-full bg-stone-100 p-3 text-stone-500">{icon || <Inbox className="h-6 w-6" aria-hidden />}</div>
      <h3 className="text-sm font-semibold text-stone-900">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-stone-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Não foi possível carregar os dados.";
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center" role="alert">
      <AlertCircle className="mb-2 h-6 w-6 text-red-700" aria-hidden />
      <p className="text-sm font-medium text-stone-800">{msg}</p>
      {onRetry && <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>Tentar novamente</Button>}
    </div>
  );
}

export function Notice({ tone = "info", title, children, icon }: { tone?: "info" | "warning" | "critical" | "good"; title?: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  const map = {
    info: "bg-sky-50 text-sky-950 ring-sky-200", warning: "bg-amber-50 text-amber-950 ring-amber-200",
    critical: "bg-red-50 text-red-950 ring-red-200", good: "bg-green-50 text-green-950 ring-green-200",
  };
  return (
    <div className={clsx("flex gap-3 rounded-lg px-4 py-3 text-sm ring-1 ring-inset", map[tone])}>
      {icon && <div className="mt-0.5 shrink-0">{icon}</div>}
      <div>
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={clsx(title && "mt-0.5", "opacity-90")}>{children}</div>}
      </div>
    </div>
  );
}
