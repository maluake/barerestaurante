import type { ReactNode } from "react";
import clsx from "clsx";
import { AlertOctagon, AlertTriangle, CheckCircle2, Info, CircleDot } from "lucide-react";

export type Tone = "neutral" | "pine" | "good" | "warning" | "serious" | "critical" | "info";

const tones: Record<Tone, string> = {
  neutral: "bg-stone-100 text-stone-700 ring-stone-200",
  pine: "bg-pine-50 text-pine-800 ring-pine-200",
  good: "bg-green-50 text-green-800 ring-green-200",
  warning: "bg-amber-50 text-amber-900 ring-amber-200",
  serious: "bg-orange-50 text-orange-900 ring-orange-200",
  critical: "bg-red-50 text-red-800 ring-red-200",
  info: "bg-sky-50 text-sky-900 ring-sky-200",
};

export function Badge({ tone = "neutral", children, className, icon }: { tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset", tones[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

const PRIORITY: Record<string, { tone: Tone; label: string; Icon: typeof Info }> = {
  critical: { tone: "critical", label: "Crítica", Icon: AlertOctagon },
  high: { tone: "serious", label: "Alta", Icon: AlertTriangle },
  medium: { tone: "warning", label: "Média", Icon: CircleDot },
  low: { tone: "neutral", label: "Baixa", Icon: Info },
};

/** Prioridade sempre com ícone + texto (nunca só cor). */
export function PriorityBadge({ priority }: { priority: string }) {
  const p = PRIORITY[priority] || PRIORITY.low;
  return <Badge tone={p.tone} icon={<p.Icon className="h-3.5 w-3.5" aria-hidden />}>{p.label}</Badge>;
}

export function StockBadge({ status }: { status: string }) {
  if (status === "out") return <Badge tone="critical" icon={<AlertOctagon className="h-3.5 w-3.5" />}>Sem estoque</Badge>;
  if (status === "low") return <Badge tone="warning" icon={<AlertTriangle className="h-3.5 w-3.5" />}>Abaixo do mínimo</Badge>;
  return <Badge tone="good" icon={<CheckCircle2 className="h-3.5 w-3.5" />}>Ok</Badge>;
}

const STATUS_TONES: Record<string, Tone> = {
  draft: "neutral", pending_approval: "warning", approved: "info", sent: "pine", partially_received: "warning",
  received: "good", cancelled: "neutral", open: "warning", paid: "good", closed: "good", completed: "good",
  confirmed: "info", preparing: "warning", ready: "good", dispatched: "pine", delivered: "neutral",
  consumed: "good", partial: "warning", reversed: "neutral", wasted: "serious", not_applicable: "neutral", pending: "neutral",
  resolved: "good", auto_resolved: "neutral", active: "good", archived: "neutral", depleted: "neutral", discarded: "neutral",
};

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return <Badge tone={STATUS_TONES[status] || "neutral"}>{label}</Badge>;
}
