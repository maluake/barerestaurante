import { useState } from "react";
import { api, newKey } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { Button, FormGrid, Input, Notice, Select } from "@/components/ui";
import type { Product, Uom } from "./types";

/** Entrada manual (saldo inicial, devolução de cliente, bonificação). Compras entram pelo recebimento. */
export function StockEntryForm({ product, onDone }: { product: Product; onDone: () => void }) {
  const uoms = useApi<Uom[]>("/units-of-measure/");
  const [f, setF] = useState({ type: "initial", quantity: "", unit: String(product.unit), unit_cost: String(Number(product.cost_price) || ""), lot_code: "", expires_at: "", reason: "" });
  const [key] = useState(newKey);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const save = useAction(() => api.post("/products/stock-entry/", {
    product: product.id, type: f.type, quantity: f.quantity.replace(",", "."), unit: Number(f.unit), unit_cost: f.unit_cost ? f.unit_cost.replace(",", ".") : undefined,
    lot_code: f.lot_code, expires_at: f.expires_at || null, reason: f.reason, idempotency_key: key,
  }), { success: "Entrada registrada.", onSuccess: onDone });
  const units = (uoms.data || []).map((u) => ({ value: u.id, label: u.code }));
  return (
    <div className="space-y-4">
      <Notice>Compras de fornecedores devem entrar pelo <strong>recebimento do pedido de compra</strong>, para manter custo, lote e contas a pagar.</Notice>
      <Select label="Tipo de entrada" value={f.type} onChange={set("type")} options={[{ value: "initial", label: "Saldo inicial" }, { value: "customer_return", label: "Devolução de cliente" }, { value: "adjustment", label: "Bonificação / ajuste" }]} />
      <FormGrid cols={3}>
        <Input label="Quantidade" inputMode="decimal" value={f.quantity} onChange={set("quantity")} required />
        <Select label="Unidade" value={f.unit} onChange={set("unit")} options={units} />
        <Input label="Custo unitário (R$)" inputMode="decimal" value={f.unit_cost} onChange={set("unit_cost")} hint="Na unidade informada" />
        <Input label="Lote" value={f.lot_code} onChange={set("lot_code")} />
        <Input label="Validade" type="date" value={f.expires_at} onChange={set("expires_at")} required={product.is_perishable} />
        <Input label="Motivo" value={f.reason} onChange={set("reason")} />
      </FormGrid>
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!f.quantity || (product.is_perishable && !f.expires_at)} onClick={() => save.mutate(undefined)}>Registrar entrada</Button></div>
    </div>
  );
}
