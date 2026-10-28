import { useState } from "react";
import { useParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, PackageCheck, Send, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import { api, newKey } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, date, dateTime, qty, todayISO } from "@/lib/format";
import { Badge, Button, Card, CardHeader, Checkbox, ConfirmDialog, ErrorState, Input, Modal, Notice, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import type { PO } from "./PurchaseOrders";

type Line = { order_item: number; quantity: string; unit_price: string; rejected_quantity: string; lot_code: string; expires_at: string; manufactured_at: string; notes: string };

function ReceiveForm({ po, onDone }: { po: PO; onDone: () => void }) {
  const pending = po.items.filter((i) => Number(i.pending_quantity) > 0);
  const [doc, setDoc] = useState("");
  const [closeRemaining, setCloseRemaining] = useState(false);
  const [key] = useState(newKey);
  const [lines, setLines] = useState<Line[]>(pending.map((i) => ({ order_item: i.id, quantity: String(Number(i.pending_quantity)), unit_price: String(Number(i.unit_price)),
    rejected_quantity: "", lot_code: "", expires_at: "", manufactured_at: "", notes: "" })));
  const upd = (idx: number, k: keyof Line, v: string) => setLines(lines.map((l, i) => (i === idx ? { ...l, [k]: v } : l)));
  const missingExpiry = lines.some((l, i) => pending[i].is_perishable && Number(l.quantity.replace(",", ".")) > 0 && !l.expires_at);
  const save = useAction(() => api.post(`/purchase-orders/${po.id}/receive/`, {
    document_number: doc, close_remaining: closeRemaining,
    items: lines.map((l) => ({ ...l, quantity: l.quantity.replace(",", ".") || "0", unit_price: l.unit_price.replace(",", "."), rejected_quantity: l.rejected_quantity.replace(",", ".") || "0" })),
  }, { "Idempotency-Key": key }), { success: "Recebimento registrado: lotes criados e estoque atualizado.", onSuccess: onDone });
  return (
    <div className="space-y-4">
      <Notice>Confira quantidade, preço e validade de cada item. Informe somente o que chegou: o restante continua pendente (recebimento parcial). Divergências geram ocorrências automaticamente.</Notice>
      <Input label="Nota fiscal / documento" value={doc} onChange={(e) => setDoc(e.target.value)} className="sm:w-64" />
      <div className="space-y-3">
        {pending.map((it, idx) => {
          const l = lines[idx];
          const priceDiff = Number(l.unit_price.replace(",", ".")) !== Number(it.unit_price);
          const qtyDiff = Number(l.quantity.replace(",", ".")) !== Number(it.pending_quantity);
          return (
            <div key={it.id} className="rounded-xl p-4 ring-1 ring-stone-200">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="font-semibold">{it.product_name} {it.is_perishable && <Badge tone="info">Perecível</Badge>}</div>
                <div className="text-xs text-stone-500">Pendente: {qty(it.pending_quantity, it.purchase_unit_code)} · pedido a {brl(it.unit_price)}/{it.purchase_unit_code}</div>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                <Input label="Recebido" suffix={it.purchase_unit_code} inputMode="decimal" value={l.quantity} onChange={(e) => upd(idx, "quantity", e.target.value)} />
                <Input label="Preço un. cobrado" inputMode="decimal" value={l.unit_price} onChange={(e) => upd(idx, "unit_price", e.target.value)} />
                <Input label="Recusado" inputMode="decimal" value={l.rejected_quantity} onChange={(e) => upd(idx, "rejected_quantity", e.target.value)} hint="Avaria/qualidade" />
                <Input label="Lote" value={l.lot_code} onChange={(e) => upd(idx, "lot_code", e.target.value)} />
                <Input label="Validade" type="date" value={l.expires_at} onChange={(e) => upd(idx, "expires_at", e.target.value)} min={todayISO()}
                  error={it.is_perishable && Number(l.quantity) > 0 && !l.expires_at ? "Obrigatória" : undefined} />
                <Input label="Fabricação" type="date" value={l.manufactured_at} onChange={(e) => upd(idx, "manufactured_at", e.target.value)} />
              </div>
              {(priceDiff || qtyDiff) && <p className="mt-2 flex items-center gap-1 text-xs text-amber-800"><AlertTriangle className="h-3.5 w-3.5" />{priceDiff ? "Preço diferente do pedido: será registrada uma ocorrência. " : ""}{qtyDiff ? "Quantidade diferente do pendente." : ""}</p>}
            </div>
          );
        })}
      </div>
      <Checkbox checked={closeRemaining} onChange={(e) => setCloseRemaining(e.target.checked)} label="Encerrar o pedido mesmo com itens faltando" hint="As faltas ficam registradas como ocorrência de quantidade." />
      <div className="flex justify-end"><Button loading={save.isPending} disabled={missingExpiry} onClick={() => save.mutate(undefined)} icon={<PackageCheck className="h-4 w-4" />}>Confirmar recebimento</Button></div>
    </div>
  );
}

export default function PurchaseOrderDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const q = useApi<PO>(`/purchase-orders/${id}/`);
  const [receive, setReceive] = useState(false);
  const [dialog, setDialog] = useState<"" | "cancel" | "reject" | "send">("");
  const [expected, setExpected] = useState("");
  const [resolving, setResolving] = useState<number | null>(null);
  const act = useAction((v: { action: string; body?: Record<string, unknown> }) => api.post(`/purchase-orders/${id}/${v.action}/`, v.body || {}),
    { success: "Pedido atualizado.", onSuccess: () => setDialog("") });
  const resolve = useAction((v: { id: number; resolution: string }) => api.post(`/purchase-issues/${v.id}/resolve/`, { resolution: v.resolution }), { success: "Ocorrência resolvida." });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <Spinner />;
  const po = q.data;
  const actions = (
    <>
      {po.status === "draft" && can("purchases.manage") && <Button icon={<Send className="h-4 w-4" />} loading={act.isPending} onClick={() => act.mutate({ action: "submit" })}>{po.needs_approval && !can("purchases.approve") ? "Enviar para aprovação" : "Aprovar pedido"}</Button>}
      {po.status === "pending_approval" && can("purchases.approve") && <>
        <Button icon={<ThumbsUp className="h-4 w-4" />} loading={act.isPending} onClick={() => act.mutate({ action: "approve" })}>Aprovar</Button>
        <Button variant="secondary" icon={<ThumbsDown className="h-4 w-4" />} onClick={() => setDialog("reject")}>Reprovar</Button>
      </>}
      {po.status === "approved" && can("purchases.manage") && <Button icon={<Send className="h-4 w-4" />} onClick={() => setDialog("send")}>Registrar envio ao fornecedor</Button>}
      {["approved", "sent", "partially_received"].includes(po.status) && can("purchases.receive") && <Button icon={<PackageCheck className="h-4 w-4" />} onClick={() => setReceive(true)}>Receber mercadorias</Button>}
      {["draft", "pending_approval", "approved", "sent"].includes(po.status) && can("purchases.manage") && <Button variant="ghost" className="text-red-800" icon={<XCircle className="h-4 w-4" />} onClick={() => setDialog("cancel")}>Cancelar</Button>}
    </>
  );
  return (
    <div>
      <PageHeader back={{ to: "/compras/pedidos", label: "Pedidos de compra" }}
        title={<span className="flex flex-wrap items-center gap-3">Pedido #{po.number} <StatusBadge status={po.status} label={po.status_label} />{po.is_late && <Badge tone="critical">Entrega atrasada</Badge>}</span>}
        description={`${po.supplier_name} · previsão ${date(po.expected_delivery)}${po.payment_terms ? ` · pagamento ${po.payment_terms}` : ""}`} actions={actions} />
      {po.status === "pending_approval" && <div className="mb-4"><Notice tone="warning">Pedido acima do limite de aprovação configurado. Requer aprovação de um gerente ou proprietário.</Notice></div>}
      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <div className="space-y-5">
          <Card padded={false}>
            <div className="p-5 pb-2"><h2 className="font-semibold">Itens</h2></div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-y border-stone-200 bg-stone-50 text-left text-xs text-stone-500">
                  <th className="px-4 py-2 font-semibold">Produto</th><th className="px-4 py-2 text-right font-semibold">Pedido</th><th className="px-4 py-2 text-right font-semibold">Recebido</th>
                  <th className="px-4 py-2 text-right font-semibold">Preço un.</th><th className="px-4 py-2 text-right font-semibold">Total</th></tr></thead>
                <tbody className="divide-y divide-stone-100">
                  {po.items.map((i) => (
                    <tr key={i.id}>
                      <td className="px-4 py-2 font-medium">{i.product_name}</td>
                      <td className="num px-4 py-2 text-right">{qty(i.quantity, i.purchase_unit_code)}</td>
                      <td className="num px-4 py-2 text-right">{Number(i.quantity_received) >= Number(i.quantity) ? <span className="inline-flex items-center gap-1 text-green-800"><CheckCircle2 className="h-3.5 w-3.5" />{qty(i.quantity_received)}</span> : qty(i.quantity_received)}</td>
                      <td className="num px-4 py-2 text-right">{brl(i.unit_price)}</td>
                      <td className="num px-4 py-2 text-right">{brl(i.total)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="text-sm">
                  <tr><td colSpan={4} className="px-4 py-1.5 text-right text-stone-500">Itens</td><td className="num px-4 py-1.5 text-right">{brl(po.items_total)}</td></tr>
                  <tr><td colSpan={4} className="px-4 py-1.5 text-right text-stone-500">Frete</td><td className="num px-4 py-1.5 text-right">{brl(po.freight)}</td></tr>
                  {Number(po.discount) > 0 && <tr><td colSpan={4} className="px-4 py-1.5 text-right text-stone-500">Desconto</td><td className="num px-4 py-1.5 text-right">−{brl(po.discount)}</td></tr>}
                  <tr className="font-bold"><td colSpan={4} className="px-4 py-2 text-right">Total</td><td className="num px-4 py-2 text-right">{brl(po.total)}</td></tr>
                </tfoot>
              </table>
            </div>
          </Card>
          {po.receipts.length > 0 && (
            <Card>
              <CardHeader title="Recebimentos" />
              <div className="space-y-4">
                {po.receipts.map((r) => (
                  <div key={r.id} className="rounded-lg p-3 ring-1 ring-stone-200">
                    <div className="mb-2 flex flex-wrap justify-between gap-2 text-sm"><span className="font-semibold">NF {r.document_number || "s/n"} · {dateTime(r.received_at)}</span><span className="text-stone-500">por {r.received_by_name} · {brl(r.total)}</span></div>
                    <ul className="space-y-1 text-sm text-stone-700">
                      {r.items.map((i) => <li key={i.id}>{qty(i.quantity, i.purchase_unit_code)} {i.product_name} a {brl(i.unit_price)}{i.lot_code ? ` · lote ${i.lot_code}` : ""}{i.expires_at ? ` · val. ${date(i.expires_at)}` : ""}{Number(i.rejected_quantity) > 0 ? ` · ${qty(i.rejected_quantity)} recusado(s)` : ""}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {po.issues.length > 0 && (
            <Card>
              <CardHeader title="Ocorrências e divergências" />
              <ul className="divide-y divide-stone-100">
                {po.issues.map((i) => (
                  <li key={i.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="text-sm">
                      <div className="flex items-center gap-2"><Badge tone={i.status === "open" ? "warning" : "good"}>{i.kind_label}</Badge>{i.product_name && <span className="font-medium">{i.product_name}</span>}</div>
                      <p className="mt-1 text-stone-700">{i.description}</p>
                      {(i.expected || i.actual) && <p className="text-xs text-stone-500">Esperado: {i.expected || "—"} · Recebido: {i.actual || "—"}</p>}
                      {i.resolution && <p className="text-xs text-green-800">Resolução: {i.resolution}</p>}
                    </div>
                    {i.status === "open" && can("purchases.receive") && <Button size="sm" variant="secondary" onClick={() => setResolving(i.id)}>Resolver</Button>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
        <Card>
          <CardHeader title="Histórico" />
          <ol className="relative space-y-4 border-l border-stone-200 pl-4">
            {po.history.map((h, i) => <li key={i} className="text-sm"><span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-pine-600 ring-4 ring-white" /><div className="font-medium">{h.label}</div><div className="text-xs text-stone-500">{dateTime(h.at)}{h.user ? ` · ${h.user}` : ""}</div></li>)}
          </ol>
          {po.notes && <p className="mt-5 whitespace-pre-line text-sm text-stone-600">{po.notes}</p>}
        </Card>
      </div>
      <Modal open={receive} onOpenChange={setReceive} title={`Receber pedido #${po.number}`} size="xl">{receive && <ReceiveForm po={po} onDone={() => setReceive(false)} />}</Modal>
      <ConfirmDialog open={resolving !== null} onOpenChange={(v) => !v && setResolving(null)} title="Resolver ocorrência" requireReason reasonLabel="Como foi resolvida?"
        loading={resolve.isPending} confirmLabel="Marcar como resolvida" description="Ex.: fornecedor emitiu nota de crédito, item reenviado, desconto na próxima compra."
        onConfirm={(resolution) => resolving && resolve.mutate({ id: resolving, resolution }, { onSuccess: () => setResolving(null) })} />
      <ConfirmDialog open={dialog === "cancel"} onOpenChange={(v) => !v && setDialog("")} title="Cancelar pedido de compra" danger requireReason loading={act.isPending} confirmLabel="Cancelar pedido"
        onConfirm={(reason) => act.mutate({ action: "cancel", body: { reason } })} />
      <ConfirmDialog open={dialog === "reject"} onOpenChange={(v) => !v && setDialog("")} title="Reprovar pedido" requireReason loading={act.isPending} confirmLabel="Reprovar"
        description="O pedido volta para rascunho para ajustes." onConfirm={(reason) => act.mutate({ action: "reject", body: { reason } })} />
      <ConfirmDialog open={dialog === "send"} onOpenChange={(v) => !v && setDialog("")} title="Registrar envio ao fornecedor" loading={act.isPending} confirmLabel="Registrar envio"
        description="Registre aqui depois de enviar o pedido ao fornecedor (telefone, e-mail ou aplicativo)." onConfirm={() => act.mutate({ action: "send", body: { expected_delivery: expected || undefined } })}>
        <Input label="Previsão de entrega" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} hint="Em branco: prazo padrão do fornecedor" />
      </ConfirmDialog>
    </div>
  );
}
