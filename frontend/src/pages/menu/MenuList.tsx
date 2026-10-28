import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Plus } from "lucide-react";
import type { Page } from "@/lib/api";
import { useApi, useDebounced, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, pct } from "@/lib/format";
import { Badge, Button, Card, DataTable, PageHeader, Pagination, SearchInput, Select, Toolbar } from "@/components/ui";
import type { MenuItem } from "@/components/domain/types";

const MODE: Record<string, string> = { recipe: "Ficha técnica", direct: "Revenda", none: "Sem baixa" };

export default function MenuList() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [missing, setMissing] = useState("");
  const [page, setPage] = useState(1);
  const cats = useOptions("/menu-categories/");
  const s = useDebounced(search);
  const q = useApi<Page<MenuItem>>("/menu-items/", { search: s || undefined, category: category || undefined, missing_recipe: missing || undefined, page });
  const showCost = can("costs.view");
  return (
    <div>
      <PageHeader title="Cardápio e fichas técnicas" description="Custo teórico por porção calculado pelos ingredientes, perdas de preparo e rendimento. Atualiza sozinho quando o custo de um insumo muda."
        actions={can("recipes.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => nav("/cardapio/novo")}>Novo item</Button>} />
      <Card padded={false}>
        <Toolbar>
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar item" className="sm:w-72" />
          <Select className="sm:w-56" value={category} onChange={(e) => setCategory(e.target.value)} options={cats.options} placeholder="Todas as categorias" aria-label="Categoria" />
          <Select className="sm:w-56" value={missing} onChange={(e) => setMissing(e.target.value)} options={[{ value: "1", label: "Sem ficha técnica" }]} placeholder="Todos os itens" aria-label="Ficha técnica" />
        </Toolbar>
        <DataTable<MenuItem> rows={q.data?.results} loading={q.isLoading} error={q.error} onRowClick={(i) => nav(`/cardapio/${i.id}`)} columns={[
          { key: "name", header: "Item", sortable: true, render: (i) => <div><div className="font-medium">{i.name}</div><div className="text-xs text-stone-500">{i.category_name || "Sem categoria"}</div></div> },
          { key: "mode", header: "Baixa de estoque", hideOnMobile: true, render: (i) => !i.has_reliable_recipe ? <Badge tone="warning" icon={<AlertTriangle className="h-3 w-3" />}>Sem ficha técnica</Badge> : <span className="text-stone-600">{MODE[i.stock_mode]}</span> },
          { key: "price", header: "Preço", align: "right", sortable: true, render: (i) => brl(i.price) },
          ...(showCost ? [
            { key: "theoretical_cost", header: "Custo/porção", align: "right" as const, sortable: true, render: (i: MenuItem) => <span>{brl(i.theoretical_cost)}{!i.cost_complete && i.stock_mode !== "none" && <span className="ml-1 text-amber-700" title="Algum ingrediente sem custo">*</span>}</span> },
            { key: "margin_percent", header: "Margem", align: "right" as const, sortable: true, sortValue: (i: MenuItem) => Number(i.margin_percent), render: (i: MenuItem) => <span>{brl(i.contribution_margin)} <span className="text-xs text-stone-500">({pct(i.margin_percent)})</span></span> },
          ] : []),
          { key: "is_available", header: "Venda", render: (i) => i.is_available ? <Badge tone="good">Disponível</Badge> : <Badge>Indisponível</Badge> },
        ]} />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
    </div>
  );
}
