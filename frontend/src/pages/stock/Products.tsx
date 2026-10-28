import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import type { Page } from "@/lib/api";
import { useApi, useDebounced, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, qty } from "@/lib/format";
import { Button, Card, DataTable, Modal, PageHeader, Pagination, SearchInput, Select, StockBadge, Toolbar, Badge } from "@/components/ui";
import { ProductForm } from "@/components/domain/ProductForm";
import type { Product } from "@/components/domain/types";

export default function Products() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [ordering, setOrdering] = useState("name");
  const [open, setOpen] = useState(false);
  const cats = useOptions("/categories/");
  const s = useDebounced(search);
  const stock = sp.get("stock") || "";
  const category = sp.get("category") || "";
  const status = sp.get("status") || "";
  const setParam = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n); setPage(1); };
  const q = useApi<Page<Product>>("/products/", { search: s || undefined, page, ordering, stock: stock || undefined, category: category || undefined, status: status || undefined });
  return (
    <div>
      <PageHeader title="Produtos" description="Insumos, bebidas e materiais. O saldo disponível exclui lotes vencidos, que ficam isolados até o descarte."
        actions={can("products.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Novo produto</Button>} />
      <Card padded={false}>
        <Toolbar>
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Nome, código, marca ou código de barras" className="sm:w-80" />
          <Select className="sm:w-48" value={category} onChange={(e) => setParam("category", e.target.value)} options={cats.options} placeholder="Todas as categorias" aria-label="Categoria" />
          <Select className="sm:w-52" value={stock} onChange={(e) => setParam("stock", e.target.value)} aria-label="Situação do estoque" placeholder="Qualquer saldo"
            options={[{ value: "low", label: "Abaixo do mínimo" }, { value: "out", label: "Sem estoque" }, { value: "expired", label: "Com lote vencido" }]} />
          <Select className="sm:w-36" value={status} onChange={(e) => setParam("status", e.target.value)} aria-label="Cadastro" placeholder="Ativos"
            options={[{ value: "archived", label: "Arquivados" }]} />
        </Toolbar>
        <DataTable<Product> rows={q.data?.results} loading={q.isLoading} error={q.error} onRetry={() => q.refetch()} sort={ordering} onSortChange={(o) => setOrdering(o || "name")}
          onRowClick={(p) => nav(`/estoque/produtos/${p.id}`)}
          columns={[
            { key: "name", header: "Produto", sortable: true, render: (p) => <div><div className="font-medium text-stone-900">{p.name}</div><div className="text-xs text-stone-500">{p.sku}{p.category_name ? ` · ${p.category_name}` : ""}</div></div> },
            { key: "quantity", header: "Disponível", align: "right", sortable: true, render: (p) => <span>{qty(p.available_quantity, p.unit_code)}{Number(p.expired_quantity) > 0 && <div className="text-xs text-red-700">+{qty(p.expired_quantity)} vencido</div>}</span> },
            { key: "min_stock", header: "Mín. / ideal", align: "right", hideOnMobile: true, render: (p) => <span className="text-stone-500">{qty(p.min_stock)} / {qty(p.ideal_stock)}</span> },
            { key: "status", header: "Situação", render: (p) => p.status === "archived" ? <Badge>Arquivado</Badge> : <StockBadge status={p.stock_status} /> },
            { key: "next_expiry", header: "Próx. validade", hideOnMobile: true, sortable: true, render: (p) => date(p.next_expiry) },
            { key: "cost_price", header: "Custo", align: "right", sortable: true, hideOnMobile: true, render: (p) => `${brl(p.cost_price)}/${p.unit_code}` },
            { key: "value", header: "Valor em estoque", align: "right", render: (p) => brl(p.stock_value) },
          ]}
        />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Novo produto" size="lg">
        {open && <ProductForm onDone={(p) => { setOpen(false); nav(`/estoque/produtos/${p.id}`); }} />}
      </Modal>
    </div>
  );
}
