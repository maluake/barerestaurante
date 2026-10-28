import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { Button, PriorityBadge } from "@/components/ui";
import { dateTime } from "@/lib/format";

export type Alert = {
  id: number; type: string; type_label: string; priority: string; title: string; reason: string; action_label: string;
  action_path: string; status: string; status_label: string; first_seen_at: string; resolved_at: string | null;
  resolved_by_name: string | null; resolution_note: string;
};

export function AlertItem({ alert, compact }: { alert: Alert; compact?: boolean }) {
  const nav = useNavigate();
  const { can } = useAuth();
  const resolve = useAction(() => api.post(`/alerts/${alert.id}/resolve/`, { note: "Resolvido pelo painel" }), { success: "Alerta marcado como resolvido." });
  return (
    <div className={compact ? "flex flex-col gap-2 py-3" : "flex flex-col gap-3 py-3.5 sm:flex-row sm:items-start"}>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <PriorityBadge priority={alert.priority} />
          <span className="text-xs text-stone-500">{alert.type_label}</span>
          {!compact && <span className="text-xs text-stone-400">· desde {dateTime(alert.first_seen_at)}</span>}
        </div>
        <p className="text-sm font-semibold text-stone-900">{alert.title}</p>
        <p className="mt-0.5 text-sm text-stone-600">{alert.reason}</p>
        {alert.status !== "open" && (
          <p className="mt-1 text-xs text-stone-500">{alert.status_label}{alert.resolved_by_name ? ` por ${alert.resolved_by_name}` : ""} em {dateTime(alert.resolved_at)}{alert.resolution_note ? ` — ${alert.resolution_note}` : ""}</p>
        )}
      </div>
      {alert.status === "open" && (
        <div className="flex shrink-0 gap-2">
          {alert.action_path && <Button size="sm" variant="secondary" onClick={() => nav(alert.action_path)}>{alert.action_label || "Abrir"}</Button>}
          {can("alerts.manage") && (
            <Button size="sm" variant="ghost" icon={<Check className="h-4 w-4" />} loading={resolve.isPending} onClick={() => resolve.mutate(undefined)} aria-label="Marcar como resolvido">
              Resolver
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
