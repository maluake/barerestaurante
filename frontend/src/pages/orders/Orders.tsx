import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Plus } from "lucide-react";
import type { Page } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime, qty, relativeMinutes, todayISO } from "@/lib/format";
import { Badge, Button, Card, DataTable, Input, Modal, PageHeader, Pagination, Select, StatusBadge, Tabs, Toolbar, SearchInput, DefinitionList } from "@/components/ui";
import { ORIGINS, type Order } from "@/components/domain/types";
import { OrderActions } from "./OrderActions";
import { useDebounced } from "@/lib/hooks";

export function OrderDetail({ order }: { order: Order }) {
  return (
    <div className="space-y-5">
      <DefinitionList items={[
        ["Origem", `${order.origin_label}${order.table_label ? ` · ${order.table_label}` : ""}`],
        ["Status", <StatusBadge status={order.status} label={order.status_label} />],
        ["Aberto em", dateTime(order.created_at)], ["Tempo", relativeMinutes(order.elapsed_minutes)],
        ["Responsável", order.created_by_name], ["Estoque", order.stock_status_label],
        ...(order.customer_name ? [["Cliente", order.customer_name] as [string, string]] : []),
        ...(order.cancel_reason ? [["Motivo do cancelamento", order.cancel_reason] as [string, string]] : []),
      ]} />
      <div>
        <h4 className="label mb-2">Itens</h4>
        <ul className="divide-y divide-stone-100 rounded-lg ring-1 ring-stone-200">
          {order.items.map((i) => (
            <li key={i.id} className="flex items-start justify-between gap-3 px-3 py-2 text-sm">
              <div>
                <span className="font-semibold">{qty(i.quantity)}×</span> {i.name}
                {i.notes && <p className="text-xs text-stone-500">Obs.: {i.notes}</p>}
                {i.stock_warning && <p className="flex items-center gap-1 text-xs text-amber-800"><AlertTriangle className="h-3 w-3" />{i.stock_warning}</p>}
              </div>
              <span className="num">{brl(Number(i.quantity) * Number(i.unit_price))}</span>
            </li>
          ))}
          <li className="flex justify-between px-3 py-2 text-sm"><span>Subtotal</span><span className="num">{brl(order.subtotal)}</span></li>
          {Number(order.discount) > 0 && <li className="flex justify-between px-3 py-2 text-sm"><span>Desconto</span><span className="num">−{brl(order.discount)}</span></li>}
          {Number(order.delivery_fee) > 0 && <li className="flex justify-between px-3 py-2 text-sm"><span>Taxa de entrega</span><span className="num">{brl(order.delivery_fee)}</span></li>}
          <li className="flex justify-between px-3 py-2 text-sm font-bold"><span>Total</span><span className="num">{brl(order.total)}</span></li>
        </ul>
        {order.notes && <p className="mt-2 text-sm text-stone-600">Observações: {order.notes}</p>}
      </div>
      <div>
        <h4 className="label mb-2">Histórico</h4>
        <ol className="space-y-1.5 text-sm">
          {order.events.map((e, i) => (
            <li key={i} className="flex gap-2"><span className="num w-28 shrink-0 text-xs text-stone-500">{dateTime(e.created_at)}</span>
              <span>{e.to_status === "received" ? "Pedido registrado" : `→ ${e.to_status}`}{e.user_name ? ` · ${e.user_name}` : ""}{e.note ? ` — ${e.note}` : ""}</span></li>
          ))}
        </ol>
      </div>
      <OrderActions order={order} size="md" />
    </div>
  );
}

export default function Orders() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState<"open" | "all">("open");
  const [origin, setOrigin] = useState("");
  const [search, setSearch] = useState("");
  const [start, setStart] = useState(todayISO());
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Order | null>(null);
  const s = useDebounced(search);
  const q = useApi<Page<Order>>("/orders/", { open: tab === "open" ? 1 : undefined, start: tab === "all" ? start : undefined, end: tab === "all" ? start : undefined,
    origin: origin || undefined, search: s || undefined, page, ordering: tab === "open" ? "created_at" : "-created_at" }, { refetchInterval: 10_000 });
  const current = sel ? q.data?.results.find((o) => o.id === sel.id) || sel : null;
  return (
    <div>
      <PageHeader title="Pedidos" description="Pedidos de balcão, mesa, retirada e entrega. Os ingredientes são baixados uma única vez, na confirmação."
        actions={can("orders.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => nav("/pedidos/novo")}>Novo pedido</Button>} />
      <Card padded={false}>
        <div className="px-4 pt-2"><Tabs value={tab} onChange={(v) => { setTab(v); setPage(1); }} items={[{ value: "open", label: "Em andamento" }, { value: "all", label: "Por dia" }]} /></div>
        <Toolbar>
          <SearchInput value={search} onChange={setSearch} placeholder="Nº, mesa ou cliente" className="sm:w-64" />
          <Select className="sm:w-48" value={origin} onChange={(e) => setOrigin(e.target.value)} options={ORIGINS} placeholder="Todas as origens" aria-label="Origem" />
          {tab === "all" && <Input type="date" className="sm:w-44" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Data" />}
        </Toolbar>
        <DataTable<Order> rows={q.data?.results} loading={q.isLoading} error={q.error} onRowClick={setSel}
          columns={[
            { key: "number", header: "Nº", render: (o) => <span className="font-semibold">#{o.number}</span> },
            { key: "origin", header: "Origem", render: (o) => <span>{o.origin_label}{o.table_label && <span className="text-stone-500"> · {o.table_label}</span>}</span> },
            { key: "items", header: "Itens", hideOnMobile: true, render: (o) => <span className="line-clamp-1 text-stone-600">{o.items.map((i) => `${Number(i.quantity)}× ${i.name}`).join(", ")}</span> },
            { key: "status", header: "Status", render: (o) => <div className="flex items-center gap-1.5"><StatusBadge status={o.status} label={o.status_label} />{o.is_late && <Badge tone="critical" icon={<AlertTriangle className="h-3 w-3" />}>Atrasado</Badge>}</div> },
            { key: "elapsed", header: "Tempo", align: "right", render: (o) => relativeMinutes(o.elapsed_minutes) },
            { key: "total", header: "Total", align: "right", render: (o) => brl(o.total) },
          ]}
          empty={<div className="py-10 text-center text-sm text-stone-500">{tab === "open" ? "Nenhum pedido em andamento." : "Nenhum pedido neste dia."} {can("orders.manage") && <Link to="/pedidos/novo" className="link">Registrar pedido</Link>}</div>}
        />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <Modal open={!!current} onOpenChange={(v) => !v && setSel(null)} title={current ? `Pedido #${current.number}` : ""} size="md">
        {current && <OrderDetail order={current} />}
      </Modal>
    </div>
  );
}
