import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api, newKey, type Page } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime, qty } from "@/lib/format";
import { Button, Card, DataTable, EmptyState, Input, Modal, Notice, PageHeader, Select, Textarea } from "@/components/ui";
import type { Product } from "@/components/domain/types";

type T = { id: number; from_unit_name: string; to_unit_name: string; notes: string; user_name: string | null; created_at: string;
  items: { product_name: string; unit_code: string; quantity: string; total_cost: string }[] };

function TransferForm({ onDone }: { onDone: () => void }) {
  const { units, unit } = useAuth();
  const products = useApi<Page<Product>>("/products/", { page_size: 500 });
  const [to, setTo] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([{ product: "", quantity: "" }]);
  const [key] = useState(newKey);
  const save = useAction(() => api.post("/transfers/", { to_unit: Number(to), notes, items: lines.filter((l) => l.product && l.quantity).map((l) => ({ product: Number(l.product), quantity: l.quantity.replace(",", ".") })) }, { "Idempotency-Key": key }),
    { success: "Transferência registrada (saída e entrada vinculadas).", onSuccess: onDone });
  const opts = (products.data?.results || []).filter((p) => Number(p.available_quantity) > 0).map((p) => ({ value: p.id, label: `${p.name} — disp. ${qty(p.available_quantity, p.unit_code)}` }));
  return (
    <div className="space-y-4">
      <Notice>Os lotes saem por ordem de validade e chegam ao destino com a mesma validade e custo. Lotes vencidos não podem ser transferidos. Respeite a cadeia de conservação no transporte.</Notice>
      <Select label="Unidade de destino" value={to} onChange={(e) => setTo(e.target.value)} options={units.filter((u) => u.id !== unit?.id).map((u) => ({ value: u.id, label: u.name }))} placeholder="Selecione" />
      {lines.map((l, i) => (
        <div key={i} className="flex gap-2">
          <Select className="flex-1" value={l.product} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, product: e.target.value } : x)))} options={opts} placeholder="Produto" aria-label="Produto" />
          <Input className="w-28" inputMode="decimal" placeholder="Qtd." value={l.quantity} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} aria-label="Quantidade" />
          <button className="p-2 text-stone-400 hover:text-red-700" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label="Remover"><Trash2 className="h-4 w-4" /></button>
        </div>
      ))}
      <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setLines([...lines, { product: "", quantity: "" }])}>Adicionar produto</Button>
      <Textarea label="Observações" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!to || !lines.some((l) => l.product && l.quantity)} onClick={() => save.mutate(undefined)}>Transferir</Button></div>
    </div>
  );
}

export default function Transfers() {
  const { units, can } = useAuth();
  const [open, setOpen] = useState(false);
  const q = useApi<Page<T>>("/transfers/");
  return (
    <div>
      <PageHeader title="Transferências entre unidades" description="Cada transferência gera uma saída na origem e uma entrada vinculada no destino, sem criar nem perder quantidades."
        actions={can("stock.transfer") && units.length > 1 && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Nova transferência</Button>} />
      {units.length < 2 ? <Card><EmptyState title="Apenas uma unidade disponível" description="Cadastre outra unidade em Configurações para transferir mercadorias." /></Card> : (
        <Card padded={false}>
          <DataTable<T> rows={q.data?.results} loading={q.isLoading} error={q.error} columns={[
            { key: "created_at", header: "Data", render: (t) => dateTime(t.created_at) },
            { key: "route", header: "Origem → destino", render: (t) => `${t.from_unit_name} → ${t.to_unit_name}` },
            { key: "items", header: "Itens", render: (t) => t.items.map((i) => `${qty(i.quantity, i.unit_code)} ${i.product_name}`).join(", ") },
            { key: "value", header: "Valor", align: "right", render: (t) => brl(t.items.reduce((s, i) => s + Number(i.total_cost), 0)) },
            { key: "user_name", header: "Responsável", hideOnMobile: true },
          ]} />
        </Card>
      )}
      <Modal open={open} onOpenChange={setOpen} title="Nova transferência">{open && <TransferForm onDone={() => setOpen(false)} />}</Modal>
    </div>
  );
}
