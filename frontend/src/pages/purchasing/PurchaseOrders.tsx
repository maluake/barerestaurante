import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, dateTime } from "@/lib/format";
import { Badge, Button, Card, DataTable, Input, Modal, PageHeader, Pagination, Select, StatusBadge, Textarea, Toolbar } from "@/components/ui";
import type { Product, Uom } from "@/components/domain/types";

export type PO = { id: number; number: number; supplier: number; supplier_name: string; status: string; status_label: string; expected_delivery: string | null;
  freight: string; discount: string; payment_terms: string; notes: string; source: string; items_total: string; total: string; is_late: boolean; needs_approval: boolean; created_at: string;
  items: { id: number; product: number; product_name: string; product_unit: string; is_perishable: boolean; purchase_unit: number; purchase_unit_code: string;
    quantity: string; unit_price: string; quantity_received: string; pending_quantity: string; total: string }[];
  receipts: { id: number; document_number: string; received_by_name: string | null; received_at: string; total: string;
    items: { id: number; product_name: string; purchase_unit_code: string; quantity: string; unit_price: string; rejected_quantity: string; lot_code: string; expires_at: string | null }[] }[];
  issues: { id: number; kind_label: string; product_name: string | null; description: string; expected: string; actual: string; status: string; resolution: string; created_at: string }[];
  history: { label: string; at: string; user: string | null }[] };

const STATUS = [["draft", "Rascunho"], ["pending_approval", "Aguardando aprovação"], ["approved", "Aprovado"], ["sent", "Enviado"], ["partially_received", "Recebido parcialmente"], ["received", "Recebido"], ["cancelled", "Cancelado"]].map(([value, label]) => ({ value, label }));

function NewPO({ onDone }: { onDone: (po: PO) => void }) {
  const sups = useOptions("/suppliers/", "name", { is_active: true });
  const products = useApi<Page<Product>>("/products/", { page_size: 500 });
  const uoms = useApi<Uom[]>("/units-of-measure/");
  const [supplier, setSupplier] = useState("");
  const [expected, setExpected] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([{ product: "", purchase_unit: "", quantity: "", unit_price: "" }]);
  const pmap = new Map((products.data?.results || []).map((p) => [String(p.id), p]));
  const unitsFor = (pid: string) => {
    const p = pmap.get(pid);
    if (!p) return [];
    const base = (uoms.data || []).find((u) => u.id === p.unit);
    return (uoms.data || []).filter((u) => u.id === p.unit || (base && u.dimension === base.dimension && u.dimension !== "package") || p.packagings.some((x) => x.unit === u.id)).map((u) => ({ value: u.id, label: u.code }));
  };
  const save = useAction(() => api.post<PO>("/purchase-orders/", {
    supplier: Number(supplier), expected_delivery: expected || null, notes,
    items: lines.filter((l) => l.product && l.quantity).map((l) => ({ product: Number(l.product), purchase_unit: Number(l.purchase_unit || pmap.get(l.product)?.unit), quantity: l.quantity.replace(",", "."), unit_price: l.unit_price.replace(",", ".") || "0" })),
  }), { success: (po) => `Pedido #${po.number} criado como rascunho.`, onSuccess: onDone });
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Fornecedor" value={supplier} onChange={(e) => setSupplier(e.target.value)} options={sups.options} placeholder="Selecione" required />
        <Input label="Previsão de entrega" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
      </div>
      {lines.map((l, i) => {
        const upd = (k: string, v: string) => setLines(lines.map((x, j) => (j === i ? { ...x, [k]: v, ...(k === "product" ? { purchase_unit: String(pmap.get(v)?.unit ?? ""), unit_price: String(Number(pmap.get(v)?.cost_price ?? 0) || "") } : {}) } : x)));
        return (
          <div key={i} className="grid grid-cols-[1fr_auto] gap-2 sm:grid-cols-[2fr_90px_90px_110px_auto]">
            <Select value={l.product} onChange={(e) => upd("product", e.target.value)} options={(products.data?.results || []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Produto" aria-label="Produto" className="col-span-2 sm:col-span-1" />
            <Input inputMode="decimal" placeholder="Qtd." value={l.quantity} onChange={(e) => upd("quantity", e.target.value)} aria-label="Quantidade" />
            <Select value={l.purchase_unit} onChange={(e) => upd("purchase_unit", e.target.value)} options={unitsFor(l.product)} aria-label="Unidade de compra" />
            <Input inputMode="decimal" placeholder="Preço un." value={l.unit_price} onChange={(e) => upd("unit_price", e.target.value)} aria-label="Preço unitário" />
            <button className="p-2 text-stone-400 hover:text-red-700" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label="Remover"><Trash2 className="h-4 w-4" /></button>
          </div>
        );
      })}
      <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setLines([...lines, { product: "", purchase_unit: "", quantity: "", unit_price: "" }])}>Adicionar item</Button>
      <Textarea label="Observações" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!supplier || !lines.some((l) => l.product && l.quantity)} onClick={() => save.mutate(undefined)}>Criar pedido</Button></div>
    </div>
  );
}

export default function PurchaseOrders() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [status, setStatus] = useState("");
  const [late, setLate] = useState(sp.get("late") === "1");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const q = useApi<Page<PO>>("/purchase-orders/", { status: status || undefined, late: late ? 1 : undefined, page });
  return (
    <div>
      <PageHeader title="Pedidos de compra" description="Do rascunho ao recebimento: aprovação quando necessário, envio, conferência e divergências. O estoque só aumenta com o que foi efetivamente recebido."
        actions={can("purchases.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Novo pedido</Button>} />
      <Card padded={false}>
        <Toolbar>
          <Select className="sm:w-56" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} options={STATUS} placeholder="Todas as situações" aria-label="Situação" />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={late} onChange={(e) => setLate(e.target.checked)} className="rounded border-stone-300 text-pine-700" />Somente atrasados</label>
        </Toolbar>
        <DataTable<PO> rows={q.data?.results} loading={q.isLoading} error={q.error} onRowClick={(p) => nav(`/compras/pedidos/${p.id}`)} columns={[
          { key: "number", header: "Nº", render: (p) => <span className="font-semibold">#{p.number}</span> },
          { key: "supplier_name", header: "Fornecedor" },
          { key: "status", header: "Situação", render: (p) => <span className="flex items-center gap-1.5"><StatusBadge status={p.status} label={p.status_label} />{p.is_late && <Badge tone="critical" icon={<AlertTriangle className="h-3 w-3" />}>Atrasado</Badge>}</span> },
          { key: "expected_delivery", header: "Previsão", hideOnMobile: true, render: (p) => date(p.expected_delivery) },
          { key: "created_at", header: "Criado", hideOnMobile: true, render: (p) => dateTime(p.created_at) },
          { key: "total", header: "Total", align: "right", render: (p) => brl(p.total) },
        ]} />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Novo pedido de compra" size="lg">{open && <NewPO onDone={(po) => { setOpen(false); nav(`/compras/pedidos/${po.id}`); }} />}</Modal>
    </div>
  );
}
