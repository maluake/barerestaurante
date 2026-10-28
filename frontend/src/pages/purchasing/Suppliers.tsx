import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Upload } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useAction, useApi, useDebounced } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl } from "@/lib/format";
import { Badge, Button, Card, DataTable, Modal, Notice, PageHeader, Pagination, SearchInput, Toolbar } from "@/components/ui";
import { SupplierForm, type Supplier } from "./SupplierForm";

export default function Suppliers() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<{ created: number; skipped_existing: number; errors: { linha: number; erro: unknown }[] } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const s = useDebounced(search);
  const q = useApi<Page<Supplier>>("/suppliers/", { search: s || undefined, page });
  const imp = useAction(async (f: File) => { const fd = new FormData(); fd.append("file", f); return api.post<typeof result>("/suppliers/import/", fd); },
    { success: "Importação concluída.", onSuccess: setResult });
  return (
    <div>
      <PageHeader title="Fornecedores" description="Fornecedores são compartilhados entre as unidades. Cadastre manualmente ou importe uma lista em CSV."
        actions={can("suppliers.manage") && <>
          <input ref={file} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) imp.mutate(f); e.target.value = ""; }} />
          <Button variant="secondary" icon={<Upload className="h-4 w-4" />} loading={imp.isPending} onClick={() => file.current?.click()}>Importar CSV</Button>
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Novo fornecedor</Button>
        </>} />
      {result && <div className="mb-4"><Notice tone={result.errors.length ? "warning" : "good"} title={`${result.created} fornecedor(es) criados · ${result.skipped_existing} já existiam`}>
        {result.errors.length > 0 && result.errors.map((e) => `Linha ${e.linha}: ${typeof e.erro === "string" ? e.erro : JSON.stringify(e.erro)}`).join(" · ")}
        {!result.errors.length && "Colunas aceitas: nome, nome_fantasia, cnpj, contato, telefone, whatsapp, email, endereco, bairro, cidade, uf, pedido_minimo, prazo_entrega_dias, taxa_entrega, condicoes_pagamento, observacoes."}
      </Notice></div>}
      <Card padded={false}>
        <Toolbar><SearchInput value={search} onChange={setSearch} placeholder="Nome, CNPJ, cidade, bairro ou contato" className="sm:w-80" /></Toolbar>
        <DataTable<Supplier> rows={q.data?.results} loading={q.isLoading} error={q.error} onRowClick={(r) => nav(`/compras/fornecedores/${r.id}`)} columns={[
          { key: "name", header: "Fornecedor", render: (r) => <div><div className="flex items-center gap-2 font-medium">{r.trade_name || r.name}{r.is_demo && <Badge tone="warning">Fictício</Badge>}{!r.is_active && <Badge>Inativo</Badge>}</div><div className="text-xs text-stone-500">{r.category_names.join(", ")}</div></div> },
          { key: "city", header: "Local", hideOnMobile: true, render: (r) => [r.neighborhood, r.city].filter(Boolean).join(" · ") || "—" },
          { key: "contact", header: "Contato", hideOnMobile: true, render: (r) => r.phone || r.email || "—" },
          { key: "delivery_days", header: "Prazo", align: "right", render: (r) => `${r.delivery_days} dia(s)` },
          { key: "min_order_value", header: "Pedido mínimo", align: "right", hideOnMobile: true, render: (r) => brl(r.min_order_value) },
          { key: "rating", header: "Avaliação", align: "right", hideOnMobile: true, render: (r) => r.quality_rating ? `Q ${r.quality_rating}/5 · P ${r.punctuality_rating ?? "—"}/5` : "—" },
        ]} />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Novo fornecedor" size="lg">{open && <SupplierForm onDone={(s) => { setOpen(false); nav(`/compras/fornecedores/${s.id}`); }} />}</Modal>
    </div>
  );
}
