import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, num } from "@/lib/format";
import { Badge, Button, Card, CardHeader, ConfirmDialog, DataTable, DefinitionList, Modal, Notice, PageHeader, Spinner, Stat } from "@/components/ui";
import { SupplierForm, type Supplier } from "./SupplierForm";

type History = { orders: { id: number; number: number; status: string; total: string; created_at: string; expected_delivery: string | null }[];
  metrics: { orders: number; total_received: string; on_time_rate: number | null; deliveries_evaluated: number; issues: number; issues_by_kind: Record<string, number> };
  products: { product_id: number; product__name: string; n: number }[] };

export default function SupplierDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const q = useApi<Supplier>(`/suppliers/${id}/`);
  const h = useApi<History>(`/suppliers/${id}/history/`);
  const [edit, setEdit] = useState(false);
  const [del, setDel] = useState(false);
  const remove = useAction(() => api.del(`/suppliers/${id}/`), { success: "Fornecedor removido ou inativado (se tiver histórico).", onSuccess: () => setDel(false) });
  if (!q.data) return <Spinner />;
  const s = q.data;
  return (
    <div>
      <PageHeader back={{ to: "/compras/fornecedores", label: "Fornecedores" }}
        title={<span className="flex flex-wrap items-center gap-2">{s.trade_name || s.name}{s.is_demo && <Badge tone="warning">Fictício</Badge>}{!s.is_active && <Badge>Inativo</Badge>}</span>}
        description={[s.name !== s.trade_name && s.trade_name ? s.name : null, s.cnpj && `CNPJ ${s.cnpj}`].filter(Boolean).join(" · ")}
        actions={can("suppliers.manage") && <>
          <Button variant="secondary" icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(true)}>Editar</Button>
          {s.is_active && <Button variant="ghost" className="text-red-800" onClick={() => setDel(true)}>Remover</Button>}
        </>} />
      {s.is_demo && <div className="mb-4"><Notice tone="warning">Fornecedor fictício criado para demonstração. Endereço, contatos e preços não correspondem a empresas reais.</Notice></div>}
      {h.data && (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Card><Stat label="Pedidos" value={h.data.metrics.orders} /></Card>
          <Card><Stat label="Total recebido" value={brl(h.data.metrics.total_received)} /></Card>
          <Card><Stat label="Pontualidade" value={h.data.metrics.on_time_rate === null ? "—" : `${num(h.data.metrics.on_time_rate, 1)}%`} hint={`${h.data.metrics.deliveries_evaluated} entrega(s) avaliadas`} /></Card>
          <Card><Stat label="Ocorrências" value={h.data.metrics.issues} tone={h.data.metrics.issues ? "warn" : "default"} /></Card>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <CardHeader title="Cadastro" />
          <DefinitionList items={[
            ["Contato", s.contact_name], ["Telefone", s.phone], ["WhatsApp", s.whatsapp], ["E-mail", s.email],
            ["Endereço", [s.address, s.neighborhood, s.city, s.state].filter(Boolean).join(", ")],
            ["Localização", s.latitude && s.longitude ? `${s.latitude}, ${s.longitude}` : "—"],
            ["Pedido mínimo", brl(s.min_order_value)], ["Prazo de entrega", `${s.delivery_days} dia(s)`], ["Taxa de entrega", brl(s.delivery_fee)],
            ["Pagamento", s.payment_terms], ["Qualidade", s.quality_rating ? `${s.quality_rating}/5` : "—"], ["Pontualidade", s.punctuality_rating ? `${s.punctuality_rating}/5` : "—"],
            ["Categorias", s.category_names.join(", ")],
          ]} />
          {s.notes && <p className="mt-4 whitespace-pre-line text-sm text-stone-600">{s.notes}</p>}
        </Card>
        <Card padded={false} className="lg:col-span-2">
          <div className="p-5 pb-2"><h2 className="font-semibold">Histórico de compras</h2></div>
          <DataTable rows={h.data?.orders} loading={h.isLoading} dense columns={[
            { key: "number", header: "Pedido", render: (o) => <Link className="link" to={`/compras/pedidos/${o.id}`}>#{o.number}</Link> },
            { key: "status", header: "Situação" }, { key: "created_at", header: "Data", render: (o) => date(o.created_at.slice(0, 10)) },
            { key: "expected_delivery", header: "Previsão", render: (o) => date(o.expected_delivery) },
            { key: "total", header: "Total", align: "right", render: (o) => brl(o.total) },
          ]} />
          <div className="border-t border-stone-100 p-5">
            <h3 className="mb-2 text-sm font-semibold">Produtos cotados</h3>
            <div className="flex flex-wrap gap-2">{h.data?.products.map((p) => <Badge key={p.product_id}>{p.product__name} ({p.n})</Badge>)}</div>
          </div>
        </Card>
      </div>
      <Modal open={edit} onOpenChange={setEdit} title="Editar fornecedor" size="lg">{edit && <SupplierForm supplier={s} onDone={() => setEdit(false)} />}</Modal>
      <ConfirmDialog open={del} onOpenChange={setDel} title="Remover fornecedor?" danger confirmLabel="Remover" loading={remove.isPending}
        description="Fornecedores com pedidos de compra são apenas inativados, preservando o histórico." onConfirm={() => remove.mutate(undefined)} />
    </div>
  );
}
