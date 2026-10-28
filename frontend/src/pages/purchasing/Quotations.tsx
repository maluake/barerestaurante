import { useState } from "react";
import { Plus } from "lucide-react";
import { api, ApiError, type Page } from "@/lib/api";
import { useAction, useApi, useDebounced, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, todayISO } from "@/lib/format";
import { Badge, Button, ConfirmDialog, Card, DataTable, FormGrid, Input, Modal, PageHeader, Pagination, SearchInput, Select, Toolbar } from "@/components/ui";
import type { Product, Uom } from "@/components/domain/types";

type Q = { id: number; supplier_name: string; supplier_is_demo: boolean; product: number; product_name: string; product_unit: string; price: string; purchase_unit_code: string;
  min_quantity: string; available_quantity: string | null; freight: string; discount_percent: string; valid_until: string | null; delivery_days: number | null; brand: string;
  quoted_at: string; age_days: number; is_stale: boolean; is_expired: boolean; payment_terms: string; product_expiry: string | null };

function QuoteForm({ onDone }: { onDone: () => void }) {
  const sups = useOptions("/suppliers/", "name", { is_active: true });
  const products = useApi<Page<Product>>("/products/", { page_size: 500 });
  const uoms = useApi<Uom[]>("/units-of-measure/");
  const [f, setF] = useState({ supplier: "", product: "", price: "", purchase_unit: "", min_quantity: "1", available_quantity: "", freight: "0", discount_percent: "0",
    valid_until: "", delivery_days: "", payment_terms: "", brand: "", product_expiry: "", quoted_at: todayISO(), notes: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const prod = products.data?.results.find((p) => String(p.id) === f.product);
  const base = uoms.data?.find((u) => u.id === prod?.unit);
  const units = (uoms.data || []).filter((u) => !prod || u.id === prod.unit || (base && u.dimension === base.dimension && u.dimension !== "package") || prod.packagings.some((x) => x.unit === u.id)).map((u) => ({ value: u.id, label: u.code }));
  const d = (v: string) => (v ? v.replace(",", ".") : null);
  const save = useAction(() => api.post("/quotations/", { ...f, supplier: Number(f.supplier), product: Number(f.product), purchase_unit: Number(f.purchase_unit || prod?.unit),
    price: d(f.price), min_quantity: d(f.min_quantity) || "1", available_quantity: d(f.available_quantity), freight: d(f.freight) || "0", discount_percent: d(f.discount_percent) || "0",
    valid_until: f.valid_until || null, delivery_days: f.delivery_days || null, product_expiry: f.product_expiry || null }), { success: "Cotação registrada.", onSuccess: onDone });
  return (
    <div className="space-y-4">
      <FormGrid>
        <Select label="Fornecedor" value={f.supplier} onChange={set("supplier")} options={sups.options} placeholder="Selecione" required />
        <Select label="Produto" value={f.product} onChange={(e) => setF({ ...f, product: e.target.value, purchase_unit: String(products.data?.results.find((p) => String(p.id) === e.target.value)?.unit ?? "") })}
          options={(products.data?.results || []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Selecione" required />
      </FormGrid>
      <FormGrid cols={4}>
        <Input label="Preço (R$)" inputMode="decimal" value={f.price} onChange={set("price")} error={errors.price} required />
        <Select label="Por" value={f.purchase_unit} onChange={set("purchase_unit")} options={units} error={errors.purchase_unit} hint="Embalagens exigem cadastro no produto" />
        <Input label="Qtd. mínima" inputMode="decimal" value={f.min_quantity} onChange={set("min_quantity")} />
        <Input label="Disponível" hint="Opcional" inputMode="decimal" value={f.available_quantity} onChange={set("available_quantity")} />
        <Input label="Frete (R$)" hint="0 = taxa padrão do fornecedor" inputMode="decimal" value={f.freight} onChange={set("freight")} />
        <Input label="Desconto (%)" inputMode="decimal" value={f.discount_percent} onChange={set("discount_percent")} error={errors.discount_percent} />
        <Input label="Prazo de entrega (dias)" inputMode="numeric" value={f.delivery_days} onChange={set("delivery_days")} />
        <Input label="Pagamento" value={f.payment_terms} onChange={set("payment_terms")} />
        <Input label="Data da consulta" type="date" value={f.quoted_at} onChange={set("quoted_at")} error={errors.quoted_at} required />
        <Input label="Cotação válida até" type="date" value={f.valid_until} onChange={set("valid_until")} />
        <Input label="Marca" value={f.brand} onChange={set("brand")} />
        <Input label="Validade do produto" type="date" value={f.product_expiry} onChange={set("product_expiry")} />
      </FormGrid>
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!f.supplier || !f.product || !f.price}
        onClick={() => { setErrors({}); save.mutate(undefined, { onError: (e) => e instanceof ApiError && setErrors(e.fieldErrors) }); }}>Salvar cotação</Button></div>
    </div>
  );
}

export default function Quotations() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [supplier, setSupplier] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [delId, setDelId] = useState<number | null>(null);
  const sups = useOptions("/suppliers/");
  const s = useDebounced(search);
  const q = useApi<Page<Q>>("/quotations/", { search: s || undefined, supplier: supplier || undefined, page });
  const del = useAction((id: number) => api.del(`/quotations/${id}/`), { success: "Cotação excluída.", onSuccess: () => setDelId(null) });
  return (
    <div>
      <PageHeader title="Cotações" description="Cada cotação tem data de referência. Valores antigos são sinalizados para não serem tratados como atuais."
        actions={can("suppliers.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Nova cotação</Button>} />
      <Card padded={false}>
        <Toolbar>
          <SearchInput value={search} onChange={setSearch} placeholder="Produto, fornecedor ou marca" className="sm:w-72" />
          <Select className="sm:w-60" value={supplier} onChange={(e) => setSupplier(e.target.value)} options={sups.options} placeholder="Todos os fornecedores" aria-label="Fornecedor" />
        </Toolbar>
        <DataTable<Q> rows={q.data?.results} loading={q.isLoading} error={q.error} dense columns={[
          { key: "product_name", header: "Produto", render: (r) => <span className="font-medium">{r.product_name}</span> },
          { key: "supplier_name", header: "Fornecedor", render: (r) => <span>{r.supplier_name}{r.supplier_is_demo && <span className="ml-1 text-xs text-amber-700">(fictício)</span>}</span> },
          { key: "price", header: "Preço", align: "right", render: (r) => `${brl(r.price)}/${r.purchase_unit_code}` },
          { key: "conditions", header: "Condições", hideOnMobile: true, render: (r) => <span className="text-xs text-stone-600">mín. {Number(r.min_quantity)} {r.purchase_unit_code}{Number(r.discount_percent) ? ` · ${Number(r.discount_percent)}% desc.` : ""}{r.delivery_days !== null ? ` · ${r.delivery_days}d` : ""}{r.brand ? ` · ${r.brand}` : ""}</span> },
          { key: "quoted_at", header: "Consulta", render: (r) => <span className="inline-flex items-center gap-1.5">{date(r.quoted_at)}{r.is_stale && <Badge tone="warning">{r.age_days} dias</Badge>}</span> },
          { key: "valid_until", header: "Validade", render: (r) => r.is_expired ? <Badge tone="critical">Vencida</Badge> : date(r.valid_until) },
          { key: "act", header: "", align: "right", render: (r) => can("suppliers.manage") && <Button size="sm" variant="ghost" onClick={() => setDelId(r.id)}>Excluir</Button> },
        ]} />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Nova cotação" size="lg">{open && <QuoteForm onDone={() => setOpen(false)} />}</Modal>
      <ConfirmDialog open={delId !== null} onOpenChange={(v) => !v && setDelId(null)} title="Excluir cotação?" danger confirmLabel="Excluir" loading={del.isPending} onConfirm={() => delId && del.mutate(delId)} />
    </div>
  );
}
