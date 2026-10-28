import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Info, ShoppingCart, Sparkles } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, dateTime, qty } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, Notice, PageHeader, Select, Spinner } from "@/components/ui";

type Item = { id: number; product: number; product_name: string; product_unit: string; min_stock: string; suggested_quantity: string; quantity: string;
  available_quantity: string; forecast_consumption: string; reorder_date: string | null; supplier: number | null; supplier_name: string | null;
  quotation: number | null; estimated_cost: string; justification: string; confidence: "good" | "limited"; selected: boolean };
type SL = { id: number; status: string; created_by_name: string | null; created_at: string; parameters: { coverage_days: number }; items: Item[]; total: string };

function Row({ item, listId, editable }: { item: Item; listId: number; editable: boolean }) {
  const sups = useOptions("/suppliers/", "name", { is_active: true });
  const [q, setQ] = useState(String(Number(item.quantity)));
  const upd = useAction((body: Record<string, unknown>) => api.patch(`/shopping-lists/${listId}/items/${item.id}/`, body));
  return (
    <li className={`grid gap-3 p-4 lg:grid-cols-[auto_1.2fr_1fr_1.6fr] lg:items-start ${!item.selected ? "opacity-60" : ""}`}>
      <input type="checkbox" className="mt-1 h-4 w-4 rounded border-stone-300 text-pine-700" checked={item.selected} disabled={!editable}
        onChange={(e) => upd.mutate({ selected: e.target.checked })} aria-label={`Incluir ${item.product_name}`} />
      <div>
        <div className="font-semibold">{item.product_name}</div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-stone-500">
          <span>Disponível: <strong className="text-stone-700">{qty(item.available_quantity, item.product_unit)}</strong></span>
          <span>Mínimo: {qty(item.min_stock)}</span>
          <span>Consumo previsto: {qty(item.forecast_consumption, item.product_unit)}</span>
        </div>
        {item.reorder_date && <div className="mt-1 text-xs"><Badge tone="warning">Abaixo do mínimo em {date(item.reorder_date)}</Badge></div>}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Input label="Comprar" suffix={item.product_unit} className="w-32" inputMode="decimal" value={q} disabled={!editable} onChange={(e) => setQ(e.target.value)}
          onBlur={() => q !== String(Number(item.quantity)) && upd.mutate({ quantity: q.replace(",", ".") })} />
        <Select label="Fornecedor" className="w-48" value={String(item.supplier ?? "")} disabled={!editable} options={sups.options} placeholder="Selecione"
          onChange={(e) => upd.mutate({ supplier: e.target.value ? Number(e.target.value) : null })} />
        <div className="pb-2 text-right"><div className="text-xs text-stone-500">Estimado</div><div className="num font-semibold">{brl(item.estimated_cost)}</div></div>
      </div>
      <p className="text-sm text-stone-600">
        {item.confidence === "limited" && <Badge tone="warning" className="mr-1.5">Estimativa limitada</Badge>}
        {item.justification}
      </p>
    </li>
  );
}

export default function ShoppingList() {
  const { can } = useAuth();
  const nav = useNavigate();
  const lists = useApi<Page<SL>>("/shopping-lists/");
  const [selected, setSelected] = useState<number | null>(null);
  const [coverage, setCoverage] = useState("");
  const [confirm, setConfirm] = useState(false);
  const currentId = selected ?? lists.data?.results[0]?.id ?? null;
  const sl = useApi<SL>(currentId ? `/shopping-lists/${currentId}/` : null);
  const gen = useAction(() => api.post<SL>("/shopping-lists/generate/", { coverage_days: coverage || undefined }), { success: (r) => `Lista gerada com ${r.items.length} sugestão(ões).`, onSuccess: (r) => setSelected(r.id) });
  const orders = useAction(() => api.post<{ orders: { id: number; number: number; supplier: string }[] }>(`/shopping-lists/${currentId}/create-orders/`),
    { success: (r) => `${r.orders.length} pedido(s) de compra criados como rascunho.`, onSuccess: () => nav("/compras/pedidos") });
  const editable = sl.data?.status === "open" && can("purchases.manage");
  const total = sl.data?.items.filter((i) => i.selected).reduce((s, i) => s + Number(i.estimated_cost), 0) || 0;
  return (
    <div>
      <PageHeader title="Lista inteligente de compras" description="Considera estoque disponível, consumo médio por dia de funcionamento, sazonalidade semanal, pedidos de clientes, compras pendentes nas datas previstas, prazo de entrega, validade e capacidade."
        actions={can("purchases.manage") && <>
          <Input className="w-36" inputMode="numeric" placeholder="Cobertura (dias)" value={coverage} onChange={(e) => setCoverage(e.target.value)} aria-label="Dias de cobertura" />
          <Button icon={<Sparkles className="h-4 w-4" />} loading={gen.isPending} onClick={() => gen.mutate(undefined)}>Gerar nova lista</Button>
        </>} />
      <div className="mb-4"><Notice icon={<Info className="h-4 w-4" />}>Compras pendentes não entram no estoque físico: são somadas apenas na projeção, na data prevista de entrega. Nenhum pedido é enviado sem sua revisão.</Notice></div>
      {lists.isLoading ? <Spinner /> : !currentId ? (
        <Card><EmptyState icon={<ShoppingCart className="h-6 w-6" />} title="Nenhuma lista gerada ainda" description="Gere a primeira lista: o sistema calcula o que comprar e explica o porquê de cada item." /></Card>
      ) : !sl.data ? <Spinner /> : (
        <Card padded={false}>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 p-4">
            <div>
              <Select className="w-72" value={String(currentId)} onChange={(e) => setSelected(Number(e.target.value))} aria-label="Lista"
                options={(lists.data?.results || []).map((l) => ({ value: l.id, label: `Lista #${l.id} · ${dateTime(l.created_at)}${l.status === "ordered" ? " · pedidos gerados" : ""}` }))} />
              <p className="mt-1 text-xs text-stone-500">Cobertura de {sl.data.parameters.coverage_days} dias após a entrega · gerada por {sl.data.created_by_name}</p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right"><div className="text-xs text-stone-500">Total estimado (selecionados)</div><div className="num text-xl font-bold">{brl(total)}</div></div>
              {editable && <Button disabled={!sl.data.items.some((i) => i.selected)} onClick={() => setConfirm(true)}>Gerar pedidos de compra</Button>}
            </div>
          </div>
          {sl.data.items.length === 0 ? <EmptyState title="Nada a comprar agora" description="Estoque, consumo e compras pendentes cobrem o período analisado." /> : (
            <ul className="divide-y divide-stone-100">{sl.data.items.map((i) => <Row key={i.id} item={i} listId={sl.data!.id} editable={!!editable} />)}</ul>
          )}
        </Card>
      )}
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Gerar pedidos de compra" confirmLabel="Gerar rascunhos" loading={orders.isPending}
        description="Um pedido em rascunho será criado para cada fornecedor, com as quantidades arredondadas para a unidade de compra das cotações. Você revisa e envia para aprovação depois."
        onConfirm={() => orders.mutate(undefined)} />
    </div>
  );
}
