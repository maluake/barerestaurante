import { useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";
import { AlertOctagon, Calculator, Lightbulb, ShieldAlert, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, qty } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Notice, PageHeader, Spinner, Tabs } from "@/components/ui";

type Rec = { kind: "required" | "suggestion" | "estimate"; text: string };
type LotRow = { id: number; product: number; product_name: string; unit_code: string; code: string; quantity_remaining: string; expires_at: string;
  unit_cost: string; remaining_value: string; location_name: string | null; supplier_name: string | null; days_to_expiry: number; category_name: string | null;
  daily_consumption: string; at_risk_quantity: string | null; recommendations: Rec[] };
type Bucket = { key: string; label: string; count: number; value: string; lots: LotRow[] };
type Data = { today: string; buckets: Bucket[]; safety_note: string };

const TONE: Record<string, string> = { expired: "border-red-600 bg-red-50", today: "border-orange-500 bg-orange-50" };

export default function Expiry() {
  const { can } = useAuth();
  const q = useApi<Data>("/expiry/");
  const [tab, setTab] = useState("expired");
  const [discard, setDiscard] = useState<LotRow | null>(null);
  const act = useAction((v: { id: number; notes: string }) => api.post(`/lots/${v.id}/discard/`, { notes: v.notes }),
    { success: "Descarte registrado como perda.", onSuccess: () => setDiscard(null) });
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Spinner />;
  const current = q.data.buckets.find((b) => b.key === tab) || q.data.buckets[0];
  return (
    <div>
      <PageHeader title="Validades" description="Lotes por faixa de vencimento (faixas configuráveis em Configurações). Lotes vencidos ficam fora do saldo disponível até o descarte." />
      <Notice tone="warning" icon={<ShieldAlert className="h-4 w-4" />} title="Segurança alimentar">{q.data.safety_note}</Notice>
      <div className="my-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {q.data.buckets.map((b) => (
          <button key={b.key} onClick={() => setTab(b.key)} className={clsx("card border-l-4 p-4 text-left transition-shadow hover:shadow-pop", TONE[b.key] || "border-stone-300", tab === b.key && "ring-2 ring-pine-600")}>
            <div className="text-xs font-semibold text-stone-600">{b.label}</div>
            <div className="num mt-1 text-2xl font-bold">{b.count}</div>
            <div className="num text-xs text-stone-500">{brl(b.value)}</div>
          </button>
        ))}
      </div>
      <Card padded={false}>
        <div className="px-4 pt-2"><Tabs value={tab} onChange={setTab} items={q.data.buckets.map((b) => ({ value: b.key, label: b.label, count: b.count }))} /></div>
        {current.lots.length === 0 ? <EmptyState title="Nenhum lote nesta faixa" description="Ótimo! Nada a fazer aqui por enquanto." /> : (
          <ul className="divide-y divide-stone-100">
            {current.lots.map((l) => (
              <li key={l.id} className="grid gap-4 p-4 lg:grid-cols-[1fr_1.3fr]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/estoque/produtos/${l.product}`} className="font-semibold text-stone-900 hover:underline">{l.product_name}</Link>
                    {l.days_to_expiry < 0 ? <Badge tone="critical" icon={<AlertOctagon className="h-3 w-3" />}>Vencido há {-l.days_to_expiry} dia(s)</Badge>
                      : l.days_to_expiry === 0 ? <Badge tone="serious">Vence hoje</Badge> : <Badge tone="warning">Vence em {l.days_to_expiry} dia(s)</Badge>}
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
                    <div><dt className="text-xs text-stone-500">Restante</dt><dd className="num font-medium">{qty(l.quantity_remaining, l.unit_code)}</dd></div>
                    <div><dt className="text-xs text-stone-500">Validade</dt><dd>{date(l.expires_at)}</dd></div>
                    <div><dt className="text-xs text-stone-500">Custo estimado</dt><dd className="num">{brl(l.remaining_value)}</dd></div>
                    <div><dt className="text-xs text-stone-500">Lote</dt><dd>{l.code || `#${l.id}`}</dd></div>
                    <div><dt className="text-xs text-stone-500">Local</dt><dd>{l.location_name || "—"}</dd></div>
                    <div><dt className="text-xs text-stone-500">Consumo médio</dt><dd className="num">{Number(l.daily_consumption) ? `${qty(l.daily_consumption, l.unit_code)}/dia` : "sem histórico"}</dd></div>
                  </dl>
                  {l.days_to_expiry < 0 && can("waste.manage") && (
                    <Button className="mt-3" size="sm" variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => setDiscard(l)}>Registrar descarte</Button>
                  )}
                </div>
                <ul className="space-y-1.5">
                  {l.recommendations.map((r, i) => (
                    <li key={i} className={clsx("flex gap-2 rounded-lg px-3 py-2 text-sm", r.kind === "required" ? "bg-red-50 text-red-950" : r.kind === "estimate" ? "bg-violet-50 text-violet-950" : "bg-pine-50 text-pine-950")}>
                      {r.kind === "required" ? <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" /> : r.kind === "estimate" ? <Calculator className="mt-0.5 h-4 w-4 shrink-0" /> : <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />}
                      <span><span className="font-semibold">{r.kind === "required" ? "Obrigatório: " : r.kind === "estimate" ? "Estimativa: " : "Sugestão: "}</span>{r.text}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <ConfirmDialog open={!!discard} onOpenChange={(v) => !v && setDiscard(null)} title="Registrar descarte do lote" danger confirmLabel="Descartar lote" loading={act.isPending}
        reasonLabel="Observações (opcional)"
        description={discard && `${qty(discard.quantity_remaining, discard.unit_code)} de ${discard.product_name} (${brl(discard.remaining_value)}) serão baixados como perda por vencimento.`}
        onConfirm={(notes) => discard && act.mutate({ id: discard.id, notes })} />
    </div>
  );
}
