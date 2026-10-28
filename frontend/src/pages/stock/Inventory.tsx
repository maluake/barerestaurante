import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime } from "@/lib/format";
import { Button, Card, DataTable, Input, Modal, PageHeader, Pagination, StatusBadge } from "@/components/ui";

export type InvItem = { id: number; product: number; product_name: string; unit_code: string; category_name: string | null; system_quantity: string;
  counted_quantity: string | null; difference: string | null; unit_cost: string; value_difference: string | null; counted_by_name: string | null; counted_at: string | null };
export type Inv = { id: number; status: string; status_label: string; description: string; reason: string; started_by_name: string | null; started_at: string;
  closed_by_name: string | null; closed_at: string | null; items: InvItem[];
  summary: { total_items: number; counted_items: number; items_with_difference: number; value_difference: string; loss_value: string } };

export default function Inventory() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [desc, setDesc] = useState("");
  const [cats, setCats] = useState<number[]>([]);
  const categories = useOptions("/categories/");
  const q = useApi<Page<Inv>>("/inventory-counts/", { page });
  const create = useAction(() => api.post<Inv>("/inventory-counts/", { description: desc, categories: cats }), { success: "Contagem iniciada.", onSuccess: (i) => nav(`/estoque/inventarios/${i.id}`) });
  return (
    <div>
      <PageHeader title="Inventário" description="Contagem física: compare o contado com o sistema. Ao finalizar, as diferenças viram ajustes auditáveis."
        actions={can("stock.adjust") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Nova contagem</Button>} />
      <Card padded={false}>
        <DataTable<Inv> rows={q.data?.results} loading={q.isLoading} error={q.error} onRowClick={(i) => nav(`/estoque/inventarios/${i.id}`)} columns={[
          { key: "id", header: "Nº", render: (i) => `#${i.id}` },
          { key: "description", header: "Descrição", render: (i) => i.description || "Contagem" },
          { key: "status", header: "Situação", render: (i) => <StatusBadge status={i.status} label={i.status_label} /> },
          { key: "progress", header: "Contados", align: "right", render: (i) => `${i.summary.counted_items}/${i.summary.total_items}` },
          { key: "diff", header: "Com diferença", align: "right", hideOnMobile: true, render: (i) => i.summary.items_with_difference },
          { key: "value", header: "Diferença (R$)", align: "right", render: (i) => <span className={Number(i.summary.value_difference) < 0 ? "text-red-700" : ""}>{brl(i.summary.value_difference)}</span> },
          { key: "started_at", header: "Início", hideOnMobile: true, render: (i) => `${dateTime(i.started_at)} · ${i.started_by_name}` },
        ]} />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Nova contagem" footer={<Button loading={create.isPending} onClick={() => create.mutate(undefined)}>Iniciar contagem</Button>}>
        <div className="space-y-4">
          <Input label="Descrição" placeholder="Ex.: Contagem semanal do bar" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <div>
            <p className="mb-2 text-sm font-medium text-stone-700">Categorias <span className="font-normal text-stone-500">(vazio = todos os produtos ativos)</span></p>
            <div className="flex flex-wrap gap-2">
              {categories.options.map((c) => (
                <button key={c.value} onClick={() => setCats((x) => (x.includes(Number(c.value)) ? x.filter((y) => y !== c.value) : [...x, Number(c.value)]))}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${cats.includes(Number(c.value)) ? "bg-pine-800 text-white" : "bg-stone-100 text-stone-700"}`}>{c.label}</button>
              ))}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
