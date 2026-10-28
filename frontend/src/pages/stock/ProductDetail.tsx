import { useState } from "react";
import { useParams } from "react-router-dom";
import { Archive, PackagePlus, Pencil, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, dateTime, pct, qty, toNum } from "@/lib/format";
import { Badge, Button, Card, CardHeader, ConfirmDialog, DataTable, DefinitionList, ErrorState, Input, Modal, PageHeader, Spinner, Stat, StatusBadge, StockBadge, Tabs } from "@/components/ui";
import { ProductForm } from "@/components/domain/ProductForm";
import { StockEntryForm } from "@/components/domain/StockEntryForm";
import type { Product } from "@/components/domain/types";
import { ChartCard, TimeLines } from "@/components/charts/Charts";

type Lot = { id: number; code: string; quantity_received: string; quantity_remaining: string; received_at: string; expires_at: string | null;
  unit_cost: string; supplier_name: string | null; document: string; location_name: string | null; status: string; source: string; remaining_value: string; days_to_expiry: number | null };
export type Movement = { id: number; product_name: string; unit_code: string; lot_code: string | null; type: string; type_label: string; quantity: string;
  unit_cost: string; total_cost: string; balance_after: string; reason: string; ref_type: string; ref_id: string; counterpart_unit_name: string | null;
  user_name: string; occurred_at: string; operation: number; operation_key: string; reversed: boolean; reversal_of: number | null };
type CostH = { id: number; cost: string; previous_cost: string; variation_percent: string | null; source: string; reference: string; user_name: string | null; created_at: string };

export function LotExpiry({ lot }: { lot: Lot }) {
  if (!lot.expires_at) return <span className="text-stone-400">Sem validade</span>;
  const d = lot.days_to_expiry ?? 0;
  return <span className="inline-flex items-center gap-1.5">{date(lot.expires_at)}
    {d < 0 ? <Badge tone="critical">Vencido</Badge> : d === 0 ? <Badge tone="serious">Hoje</Badge> : d <= 3 ? <Badge tone="warning">{d} dia(s)</Badge> : null}</span>;
}

export default function ProductDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const [tab, setTab] = useState<"lots" | "movements" | "costs">("lots");
  const [edit, setEdit] = useState(false);
  const [entry, setEntry] = useState(false);
  const [costOpen, setCostOpen] = useState(false);
  const [newCost, setNewCost] = useState("");
  const [del, setDel] = useState(false);
  const p = useApi<Product>(`/products/${id}/`);
  const lots = useApi<Lot[]>(tab === "lots" ? `/products/${id}/lots/` : null);
  const movs = useApi<Movement[]>(tab === "movements" ? `/products/${id}/movements/` : null);
  const costs = useApi<CostH[]>(`/products/${id}/cost-history/`);
  const archive = useAction(() => api.post(`/products/${id}/archive/`), { success: "Situação do produto atualizada." });
  const remove = useAction(() => api.del(`/products/${id}/`), { success: "Produto excluído.", onSuccess: () => history.back() });
  const setCost = useAction((reason: string) => api.post(`/products/${id}/set-cost/`, { cost: newCost.replace(",", "."), reason }),
    { success: "Custo atualizado; fichas técnicas recalculadas.", onSuccess: () => setCostOpen(false) });
  if (p.error) return <ErrorState error={p.error} />;
  if (!p.data) return <Spinner />;
  const prod = p.data;
  return (
    <div>
      <PageHeader back={{ to: "/estoque/produtos", label: "Produtos" }}
        title={<span className="flex flex-wrap items-center gap-3">{prod.name} {prod.status === "archived" ? <Badge>Arquivado</Badge> : <StockBadge status={prod.stock_status} />}</span>}
        description={`${prod.sku}${prod.category_name ? ` · ${prod.category_name}` : ""}${prod.brand ? ` · ${prod.brand}` : ""}`}
        actions={<>
          {can("stock.move") && prod.status === "active" && <Button variant="secondary" icon={<PackagePlus className="h-4 w-4" />} onClick={() => setEntry(true)}>Entrada manual</Button>}
          {can("products.manage") && <Button variant="secondary" icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(true)}>Editar</Button>}
          {can("products.manage") && <Button variant="ghost" icon={<Archive className="h-4 w-4" />} loading={archive.isPending} onClick={() => archive.mutate(undefined)}>{prod.status === "active" ? "Arquivar" : "Reativar"}</Button>}
          {can("products.manage") && <Button variant="ghost" className="text-red-800" icon={<Trash2 className="h-4 w-4" />} onClick={() => setDel(true)}>Excluir</Button>}
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Card><Stat label="Disponível" value={qty(prod.available_quantity, prod.unit_code)} hint={toNum(prod.expired_quantity) > 0 ? `${qty(prod.expired_quantity, prod.unit_code)} vencidos isolados` : `Físico: ${qty(prod.quantity, prod.unit_code)}`} tone={toNum(prod.expired_quantity) > 0 ? "warn" : "default"} /></Card>
        <Card><Stat label="Mínimo / ideal" value={`${qty(prod.min_stock)} / ${qty(prod.ideal_stock)}`} hint={prod.unit_code} /></Card>
        <Card><Stat label="Custo de reposição" value={brl(prod.cost_price)} hint={`por ${prod.unit_code} · último custo de compra`} /></Card>
        <Card><Stat label="Valor em estoque" value={brl(prod.stock_value)} /></Card>
        <Card><Stat label="Próxima validade" value={date(prod.next_expiry)} /></Card>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title="Cadastro" />
          <DefinitionList items={[
            ["Unidade de estoque", prod.unit_code], ["Local", prod.location_name], ["Fornecedor principal", prod.supplier_name],
            ["Perecível", prod.is_perishable ? `Sim${prod.shelf_life_days ? ` · validade típica ${prod.shelf_life_days} dias` : ""}` : "Não"],
            ["Capacidade máxima", prod.max_stock ? qty(prod.max_stock, prod.unit_code) : "—"], ["Código de barras", prod.barcode],
            ["Embalagens", prod.packagings.length ? prod.packagings.map((x) => `1 ${x.unit_code} = ${qty(x.quantity)} ${x.contained_unit_code}`).join(" · ") : "Nenhuma"],
            ["Cadastrado em", date(prod.created_at)],
          ]} />
          {prod.description && <p className="mt-4 text-sm text-stone-600">{prod.description}</p>}
        </Card>
        <ChartCard className="lg:col-span-2" title="Histórico de custo" help="Custo de reposição por unidade de estoque a cada mudança (recebimentos ou ajuste manual)."
          empty={!costs.data?.length} table={{ columns: ["Data", "Custo"], rows: (costs.data || []).map((c) => [dateTime(c.created_at), brl(c.cost)]) }}
          actions={can("products.manage") && <Button size="sm" variant="ghost" onClick={() => { setNewCost(String(Number(prod.cost_price))); setCostOpen(true); }}>Ajustar custo</Button>}>
          <TimeLines data={[...(costs.data || [])].reverse().map((c) => ({ date: c.created_at.slice(0, 10), Custo: toNum(c.cost) }))} xKey="date" xFmt={(v) => date(v).slice(0, 5)} fmt={brl} series={[{ key: "Custo", name: "Custo" }]} height={200} />
        </ChartCard>
      </div>
      <Card padded={false} className="mt-5">
        <div className="px-4 pt-2"><Tabs value={tab} onChange={setTab} items={[{ value: "lots", label: "Lotes ativos" }, { value: "movements", label: "Movimentações" }, { value: "costs", label: "Variações de custo" }]} /></div>
        {tab === "lots" && <DataTable<Lot> rows={lots.data} loading={lots.isLoading} dense columns={[
          { key: "code", header: "Lote", render: (l) => l.code || `#${l.id}` },
          { key: "expires_at", header: "Validade", render: (l) => <LotExpiry lot={l} /> },
          { key: "quantity_remaining", header: "Restante", align: "right", render: (l) => `${qty(l.quantity_remaining, prod.unit_code)} de ${qty(l.quantity_received)}` },
          { key: "unit_cost", header: "Custo un.", align: "right", render: (l) => brl(l.unit_cost) },
          { key: "received_at", header: "Recebido", hideOnMobile: true, render: (l) => date(l.received_at) },
          { key: "supplier_name", header: "Fornecedor", hideOnMobile: true, render: (l) => l.supplier_name || "—" },
          { key: "location_name", header: "Local", hideOnMobile: true, render: (l) => l.location_name || "—" },
          { key: "document", header: "NF", hideOnMobile: true, render: (l) => l.document || "—" },
        ]} />}
        {tab === "movements" && <MovementTable rows={movs.data} loading={movs.isLoading} />}
        {tab === "costs" && <DataTable<CostH> rows={costs.data} loading={costs.isLoading} dense columns={[
          { key: "created_at", header: "Data", render: (c) => dateTime(c.created_at) },
          { key: "previous_cost", header: "Anterior", align: "right", render: (c) => brl(c.previous_cost) },
          { key: "cost", header: "Novo", align: "right", render: (c) => brl(c.cost) },
          { key: "variation_percent", header: "Variação", align: "right", render: (c) => c.variation_percent === null ? "—" : <span className={toNum(c.variation_percent) > 0 ? "text-red-700" : "text-green-800"}>{pct(c.variation_percent)}</span> },
          { key: "source", header: "Origem", render: (c) => ({ receipt: "Recebimento", manual: "Manual", initial: "Inicial" }[c.source] || c.source) },
          { key: "reference", header: "Referência", hideOnMobile: true },
          { key: "user_name", header: "Usuário", hideOnMobile: true, render: (c) => c.user_name || "Sistema" },
        ]} />}
      </Card>
      <Modal open={edit} onOpenChange={setEdit} title="Editar produto" size="lg">{edit && <ProductForm product={prod} onDone={() => setEdit(false)} />}</Modal>
      <Modal open={entry} onOpenChange={setEntry} title={`Entrada manual · ${prod.name}`}>{entry && <StockEntryForm product={prod} onDone={() => setEntry(false)} />}</Modal>
      <ConfirmDialog open={costOpen} onOpenChange={setCostOpen} title="Ajustar custo de reposição" requireReason reasonLabel="Motivo do ajuste" loading={setCost.isPending}
        description="O custo é atualizado automaticamente a cada recebimento. Ajuste manual fica registrado no histórico e recalcula as fichas técnicas." onConfirm={(r) => setCost.mutate(r)}>
        <Input label={`Novo custo por ${prod.unit_code} (R$)`} inputMode="decimal" value={newCost} onChange={(e) => setNewCost(e.target.value)} />
      </ConfirmDialog>
      <ConfirmDialog open={del} onOpenChange={setDel} title="Excluir produto?" danger confirmLabel="Excluir" loading={remove.isPending}
        description="Produtos com movimentações ou usados em fichas técnicas não podem ser excluídos — use Arquivar." onConfirm={() => remove.mutate(undefined)} />
    </div>
  );
}

export function MovementTable({ rows, loading, showProduct, footer }: { rows?: Movement[]; loading?: boolean; showProduct?: boolean; footer?: React.ReactNode }) {
  return (
    <DataTable<Movement> rows={rows} loading={loading} dense footer={footer} columns={[
      { key: "occurred_at", header: "Data", render: (m) => dateTime(m.occurred_at) },
      ...(showProduct ? [{ key: "product_name", header: "Produto", render: (m: Movement) => <span className="font-medium">{m.product_name}</span> }] : []),
      { key: "type", header: "Tipo", render: (m) => <span className="inline-flex items-center gap-1.5">{m.type_label}{m.reversed && <StatusBadge status="reversed" label="Estornado" />}</span> },
      { key: "quantity", header: "Quantidade", align: "right", render: (m) => <span className={toNum(m.quantity) < 0 ? "text-red-700" : "text-green-800"}>{toNum(m.quantity) > 0 ? "+" : ""}{qty(m.quantity, m.unit_code)}</span> },
      { key: "total_cost", header: "Custo", align: "right", render: (m) => brl(m.total_cost) },
      { key: "balance_after", header: "Saldo", align: "right", hideOnMobile: true, render: (m) => qty(m.balance_after) },
      { key: "lot_code", header: "Lote", hideOnMobile: true, render: (m) => m.lot_code || "—" },
      { key: "reason", header: "Motivo / origem", hideOnMobile: true, render: (m) => <span className="text-stone-600">{m.reason}{m.counterpart_unit_name ? ` (${m.counterpart_unit_name})` : ""}</span> },
      { key: "user_name", header: "Responsável", hideOnMobile: true },
    ]} />
  );
}
