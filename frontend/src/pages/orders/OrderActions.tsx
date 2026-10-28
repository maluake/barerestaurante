import { useState } from "react";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { Button, ConfirmDialog, Select } from "@/components/ui";
import { PAYMENTS, STATUS_ACTION, type Order } from "@/components/domain/types";

const KITCHEN = new Set(["preparing", "ready"]);

/** Botões de próxima etapa respeitando a permissão do perfil (validada também no backend). */
export function OrderActions({ order, size = "sm", kitchenOnly }: { order: Order; size?: "sm" | "md" | "lg"; kitchenOnly?: boolean }) {
  const { can } = useAuth();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [deliverOpen, setDeliverOpen] = useState(false);
  const [payment, setPayment] = useState(order.payment_method || "pix");
  const change = useAction((v: { status: string; note?: string; payment_method?: string }) => api.post(`/orders/${order.id}/status/`, v),
    { success: `Pedido #${order.number} atualizado.` });
  const allowedNext = order.next_statuses.filter((s) => {
    if (kitchenOnly && !KITCHEN.has(s)) return false;
    if (s === "cancelled") return can("orders.manage");
    return KITCHEN.has(s) ? can("kitchen.update") || can("orders.manage") : can("orders.manage");
  });
  const primary = allowedNext.filter((s) => s !== "cancelled");
  return (
    <div className="flex flex-wrap gap-2">
      {primary.map((s, i) => (
        <Button key={s} size={size} variant={i === 0 ? "primary" : "secondary"} loading={change.isPending && change.variables?.status === s}
          onClick={() => (s === "delivered" ? setDeliverOpen(true) : change.mutate({ status: s }))}>{STATUS_ACTION[s]}</Button>
      ))}
      {allowedNext.includes("cancelled") && <Button size={size} variant="ghost" className="text-red-800" onClick={() => setCancelOpen(true)}>Cancelar</Button>}
      <ConfirmDialog open={cancelOpen} onOpenChange={setCancelOpen} title={`Cancelar pedido #${order.number}?`} danger requireReason confirmLabel="Cancelar pedido"
        loading={change.isPending}
        description={order.status === "received" ? "Nenhum ingrediente foi baixado ainda." : order.status === "confirmed"
          ? "Os ingredientes baixados voltarão ao estoque (estorno)." : "O preparo já começou: os ingredientes serão registrados como perda."}
        onConfirm={(note) => change.mutate({ status: "cancelled", note }, { onSuccess: () => setCancelOpen(false) })} />
      <ConfirmDialog open={deliverOpen} onOpenChange={setDeliverOpen} title={`Entregar pedido #${order.number}`} confirmLabel="Concluir e registrar venda"
        loading={change.isPending} description="A venda será registrada com o valor do pedido. Os ingredientes já foram baixados na confirmação."
        onConfirm={() => change.mutate({ status: "delivered", payment_method: payment }, { onSuccess: () => setDeliverOpen(false) })}>
        <Select label="Forma de pagamento" value={payment} onChange={(e) => setPayment(e.target.value)} options={PAYMENTS} />
      </ConfirmDialog>
    </div>
  );
}
