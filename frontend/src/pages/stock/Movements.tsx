import { useState } from "react";
import type { Page } from "@/lib/api";
import { api } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { Button, Card, ConfirmDialog, DataTable, Input, PageHeader, Pagination, Select, Toolbar, StatusBadge } from "@/components/ui";
import { brl, dateTime, qty, toNum } from "@/lib/format";
import type { Movement } from "./ProductDetail";

const TYPES = [
  ["receipt", "Recebimento de compra"], ["sale", "Venda"], ["production", "Consumo na produção"], ["loss", "Perda"], ["discard", "Descarte"],
  ["adjustment", "Ajuste de inventário"], ["transfer_out", "Transferência (saída)"], ["transfer_in", "Transferência (entrada)"],
  ["customer_return", "Devolução de cliente"], ["reversal", "Estorno"], ["initial", "Saldo inicial"],
].map(([value, label]) => ({ value, label }));
const REVERSIBLE = new Set(["initial", "customer_return", "loss", "discard"]);

export default function Movements() {
  const { can } = useAuth();
  const [type, setType] = useState("");
  const [product, setProduct] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [page, setPage] = useState(1);
  const [rev, setRev] = useState<Movement | null>(null);
  const products = useOptions("/products/");
  const q = useApi<Page<Movement>>("/movements/", { type: type || undefined, product: product || undefined, start: start || undefined, end: end || undefined, page });
  const reverse = useAction((reason: string) => api.post(`/stock-operations/${rev!.operation}/reverse/`, { reason }), { success: "Estorno registrado.", onSuccess: () => setRev(null) });
  return (
    <div>
      <PageHeader title="Movimentações" description="Histórico imutável de entradas e saídas. Correções são feitas por estorno ou ajuste, sempre com responsável e motivo." />
      <Card padded={false}>
        <Toolbar>
          <Select className="sm:w-56" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} options={TYPES} placeholder="Todos os tipos" aria-label="Tipo" />
          <Select className="sm:w-56" value={product} onChange={(e) => { setProduct(e.target.value); setPage(1); }} options={products.options} placeholder="Todos os produtos" aria-label="Produto" />
          <Input type="date" className="sm:w-40" value={start} onChange={(e) => setStart(e.target.value)} aria-label="De" />
          <Input type="date" className="sm:w-40" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="Até" />
        </Toolbar>
        <DataTable<Movement> rows={q.data?.results} loading={q.isLoading} error={q.error} dense columns={[
          { key: "occurred_at", header: "Data", render: (m) => dateTime(m.occurred_at) },
          { key: "product_name", header: "Produto", render: (m) => <span className="font-medium">{m.product_name}</span> },
          { key: "type", header: "Tipo", render: (m) => <span className="inline-flex items-center gap-1.5">{m.type_label}{m.reversed && <StatusBadge status="reversed" label="Estornado" />}</span> },
          { key: "quantity", header: "Quantidade", align: "right", render: (m) => <span className={toNum(m.quantity) < 0 ? "text-red-700" : "text-green-800"}>{toNum(m.quantity) > 0 ? "+" : ""}{qty(m.quantity, m.unit_code)}</span> },
          { key: "total_cost", header: "Custo", align: "right", render: (m) => brl(m.total_cost) },
          { key: "lot_code", header: "Lote", hideOnMobile: true, render: (m) => m.lot_code || "—" },
          { key: "reason", header: "Motivo", hideOnMobile: true, render: (m) => <span className="text-stone-600">{m.reason}{m.counterpart_unit_name ? ` (${m.counterpart_unit_name})` : ""}</span> },
          { key: "user_name", header: "Responsável", hideOnMobile: true },
          { key: "act", header: "", align: "right", render: (m) => can("stock.adjust") && REVERSIBLE.has(m.type) && !m.reversed && !m.ref_type.startsWith("purchase") && m.ref_type !== "inventory"
            ? <Button size="sm" variant="ghost" onClick={() => setRev(m)}>Estornar</Button> : null },
        ]} />
        {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      </Card>
      <ConfirmDialog open={!!rev} onOpenChange={(v) => !v && setRev(null)} title="Estornar operação" requireReason loading={reverse.isPending} confirmLabel="Estornar"
        description="Todas as movimentações da operação serão revertidas com novos registros de estorno. Nada é apagado." onConfirm={(r) => reverse.mutate(r)} />
    </div>
  );
}
