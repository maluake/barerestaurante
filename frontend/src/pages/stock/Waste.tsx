import { useState } from "react";
import { Lightbulb, Plus } from "lucide-react";
import { api, newKey, type Page } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime, monthStartISO, num, qty, todayISO, toNum } from "@/lib/format";
import { Button, Card, CardHeader, DataTable, Input, Modal, PageHeader, Pagination, Select, Textarea, Toolbar, Stat } from "@/components/ui";
import { ChartCard, CategoryBars, RankBars } from "@/components/charts/Charts";
import type { Product } from "@/components/domain/types";

const REASONS = [
  ["expired", "Vencido"], ["spoiled", "Estragado/impróprio"], ["preparation", "Erro ou sobra de preparo"], ["broken", "Quebra/avaria"],
  ["returned", "Devolvido pelo cliente"], ["storage", "Falha de armazenamento"], ["other", "Outro"],
].map(([value, label]) => ({ value, label }));

type W = { id: number; product_name: string; category_name: string | null; unit_code: string; lot_code: string | null; quantity: string; total_cost: string; reason_label: string; notes: string; user_name: string; occurred_at: string };
type Analysis = { total_value: string; by_product: { product__name: string; product__unit__code: string; value: string; quantity: string; records: number }[];
  by_category: { product__category__name: string | null; value: string }[]; by_reason: { label: string; value: string; records: number }[];
  suggestions: { reason: string; share_percent: string; text: string }[] };

function WasteForm({ onDone }: { onDone: () => void }) {
  const products = useApi<Page<Product>>("/products/", { page_size: 500 });
  const [f, setF] = useState({ product: "", lot: "", quantity: "", reason: "spoiled", notes: "" });
  const lots = useApi<{ id: number; code: string; quantity_remaining: string; expires_at: string | null }[]>(f.product ? `/products/${f.product}/lots/` : null);
  const [key] = useState(newKey);
  const prod = products.data?.results.find((p) => String(p.id) === f.product);
  const save = useAction(() => api.post("/waste/", { product: Number(f.product), lot: f.lot ? Number(f.lot) : null, quantity: f.quantity.replace(",", "."), reason: f.reason, notes: f.notes }, { "Idempotency-Key": key }),
    { success: "Perda registrada.", onSuccess: onDone });
  return (
    <div className="space-y-4">
      <Select label="Produto" value={f.product} onChange={(e) => setF({ ...f, product: e.target.value, lot: "" })} options={(products.data?.results || []).map((p) => ({ value: p.id, label: `${p.name} (${qty(p.available_quantity, p.unit_code)})` }))} placeholder="Selecione" required />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Quantidade" suffix={prod?.unit_code} inputMode="decimal" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} required />
        <Select label="Motivo" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} options={REASONS} />
      </div>
      <Select label="Lote" hint="Opcional. Sem lote, a baixa segue a ordem de validade (FEFO)." value={f.lot} onChange={(e) => setF({ ...f, lot: e.target.value })}
        options={(lots.data || []).map((l) => ({ value: l.id, label: `${l.code || `#${l.id}`} · ${qty(l.quantity_remaining)} · val. ${l.expires_at ? new Date(l.expires_at + "T12:00").toLocaleDateString("pt-BR") : "—"}` }))} placeholder="Automático (FEFO)" />
      <Textarea label="Observações" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!f.product || !f.quantity} onClick={() => save.mutate(undefined)}>Registrar perda</Button></div>
    </div>
  );
}

export default function Waste() {
  const { can } = useAuth();
  const [start, setStart] = useState(monthStartISO());
  const [end, setEnd] = useState(todayISO());
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const cats = useOptions("/categories/");
  const list = useApi<Page<W>>("/waste/", { start, end, reason: reason || undefined, product__category: category || undefined, page });
  const analysis = useApi<Analysis>(can("stock.view") ? "/waste/analysis/" : null, { start, end });
  const a = analysis.data;
  return (
    <div>
      <PageHeader title="Perdas e desperdício" description="Registre perdas com motivo e responsável. O sistema identifica os principais focos e sugere medidas preventivas."
        actions={can("waste.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Registrar perda</Button>} />
      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-3">
          <Input label="De" type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-40" />
          <Input label="Até" type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-40" />
          {a && <div className="ml-auto"><Stat label="Total no período" value={brl(a.total_value)} tone={toNum(a.total_value) > 0 ? "bad" : "default"} /></div>}
        </div>
      </Card>
      {a && toNum(a.total_value) > 0 && (
        <div className="mb-5 grid gap-5 lg:grid-cols-3">
          <ChartCard title="Maiores focos de perda" help="Produtos com maior custo perdido no período." table={{ columns: ["Produto", "Qtd.", "Custo"], rows: a.by_product.map((r) => [r.product__name, qty(r.quantity, r.product__unit__code), brl(r.value)]) }}>
            <RankBars data={a.by_product} labelKey="product__name" valueKey="value" fmt={brl} valueLabel="Custo perdido" />
          </ChartCard>
          <ChartCard title="Por categoria" table={{ columns: ["Categoria", "Custo"], rows: a.by_category.map((r) => [r.product__category__name || "Sem categoria", brl(r.value)]) }}>
            <CategoryBars data={a.by_category.map((r) => ({ name: r.product__category__name || "Sem categoria", value: toNum(r.value) }))} labelKey="name" valueKey="value" fmt={brl} />
          </ChartCard>
          <Card>
            <CardHeader title="Motivos e prevenção" />
            <ul className="mb-4 space-y-1.5 text-sm">{a.by_reason.map((r) => <li key={r.label} className="flex justify-between"><span>{r.label} <span className="text-stone-400">({r.records})</span></span><span className="num font-medium">{brl(r.value)}</span></li>)}</ul>
            <div className="space-y-2">
              {a.suggestions.map((s) => (
                <div key={s.reason} className="flex gap-2 rounded-lg bg-pine-50 p-3 text-sm text-pine-950">
                  <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" /><span><strong>{s.reason} ({num(s.share_percent, 1)}%):</strong> {s.text}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
      <Card padded={false}>
        <Toolbar>
          <Select className="sm:w-56" value={reason} onChange={(e) => setReason(e.target.value)} options={REASONS} placeholder="Todos os motivos" aria-label="Motivo" />
          <Select className="sm:w-56" value={category} onChange={(e) => setCategory(e.target.value)} options={cats.options} placeholder="Todas as categorias" aria-label="Categoria" />
        </Toolbar>
        <DataTable<W> rows={list.data?.results} loading={list.isLoading} error={list.error} dense columns={[
          { key: "occurred_at", header: "Data", render: (w) => dateTime(w.occurred_at) },
          { key: "product_name", header: "Produto", render: (w) => <span className="font-medium">{w.product_name}</span> },
          { key: "quantity", header: "Quantidade", align: "right", render: (w) => qty(w.quantity, w.unit_code) },
          { key: "total_cost", header: "Custo", align: "right", render: (w) => brl(w.total_cost) },
          { key: "reason_label", header: "Motivo" },
          { key: "lot_code", header: "Lote", hideOnMobile: true, render: (w) => w.lot_code || "FEFO" },
          { key: "user_name", header: "Responsável", hideOnMobile: true },
          { key: "notes", header: "Observações", hideOnMobile: true, render: (w) => <span className="text-stone-600">{w.notes}</span> },
        ]} />
        {list.data && <Pagination page={page} count={list.data.count} onChange={setPage} />}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Registrar perda">{open && <WasteForm onDone={() => setOpen(false)} />}</Modal>
    </div>
  );
}
