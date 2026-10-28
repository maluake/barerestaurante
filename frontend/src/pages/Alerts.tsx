import { useState } from "react";
import { CheckCircle2, RefreshCw } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { Button, Card, EmptyState, ErrorState, PageHeader, Select, Spinner, Tabs, Pagination } from "@/components/ui";
import { AlertItem, type Alert } from "@/components/domain/AlertItem";

const TYPES = [
  ["", "Todos os tipos"], ["low_stock", "Estoque abaixo do mínimo"], ["stockout_risk", "Pode acabar"], ["expiring", "Próximo do vencimento"],
  ["expired", "Vencido"], ["slow_order", "Pedido demorado"], ["po_approval", "Compra aguardando aprovação"], ["late_delivery", "Entrega atrasada"],
  ["quote_expiring", "Cotação vencendo"], ["cost_increase", "Aumento de custo"], ["waste_above", "Desperdício acima do padrão"],
  ["consumption_spike", "Consumo incomum"], ["inventory_divergence", "Divergência de inventário"], ["missing_recipe", "Sem ficha técnica"],
  ["negative_stock", "Saldo negativo"], ["integration_failure", "Falha de integração"],
];

export default function Alerts() {
  const [tab, setTab] = useState<"open" | "history">("open");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const params = tab === "open" ? { type: type || undefined, page } : { status__in: "resolved,auto_resolved", type: type || undefined, page, ordering: "-resolved_at" };
  const q = useApi<Page<Alert>>("/alerts/", params);
  const refresh = useAction(() => api.post<{ created: number }>("/alerts/refresh/"), { success: (r) => `Alertas recalculados. Novos: ${r.created}.` });
  return (
    <div>
      <PageHeader title="Atenção" description="Alertas gerados a partir dos dados reais. Alertas resolvidos não reaparecem por 24 horas; os que deixam de existir são encerrados automaticamente."
        actions={<Button variant="secondary" icon={<RefreshCw className="h-4 w-4" />} loading={refresh.isPending} onClick={() => refresh.mutate(undefined)}>Recalcular agora</Button>} />
      <Card padded={false}>
        <div className="flex flex-col gap-3 px-4 pt-3 sm:flex-row sm:items-end sm:justify-between">
          <Tabs value={tab} onChange={(v) => { setTab(v); setPage(1); }} className="border-none" items={[{ value: "open", label: "Em aberto" }, { value: "history", label: "Histórico" }]} />
          <Select className="sm:w-64" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} options={TYPES.map(([v, l]) => ({ value: v, label: l }))} aria-label="Filtrar por tipo" />
        </div>
        <div className="px-4">
          {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Spinner /> : q.data.results.length === 0 ? (
            <EmptyState icon={<CheckCircle2 className="h-6 w-6 text-green-700" />} title={tab === "open" ? "Nenhum alerta em aberto" : "Sem histórico"} description="Quando algo precisar da sua atenção, aparecerá aqui com o motivo e uma ação sugerida." />
          ) : (
            <div className="divide-y divide-stone-100">{q.data.results.map((a) => <AlertItem key={a.id} alert={a} />)}</div>
          )}
        </div>
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
    </div>
  );
}
