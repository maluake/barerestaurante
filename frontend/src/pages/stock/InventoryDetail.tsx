import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime, qty, toNum } from "@/lib/format";
import { Button, Card, ConfirmDialog, ErrorState, Notice, PageHeader, SearchInput, Spinner, Stat, StatusBadge } from "@/components/ui";
import type { Inv } from "./Inventory";

export default function InventoryDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const q = useApi<Inv>(`/inventory-counts/${id}/`);
  const [values, setValues] = useState<Record<number, string>>({});
  const [search, setSearch] = useState("");
  const [closeOpen, setCloseOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  useEffect(() => {
    if (q.data) setValues(Object.fromEntries(q.data.items.map((i) => [i.id, i.counted_quantity === null ? "" : String(Number(i.counted_quantity))])));
  }, [q.data]);
  const save = useAction(() => api.post(`/inventory-counts/${id}/count/`, { items: Object.entries(values).map(([k, v]) => ({ id: Number(k), counted_quantity: v })) }), { success: "Contagem salva." });
  const close = useAction((reason: string) => api.post(`/inventory-counts/${id}/count/`, { items: Object.entries(values).map(([k, v]) => ({ id: Number(k), counted_quantity: v })) })
    .then(() => api.post(`/inventory-counts/${id}/close/`, { reason })), { success: "Inventário finalizado e ajustes registrados.", onSuccess: () => setCloseOpen(false) });
  const cancel = useAction(() => api.post(`/inventory-counts/${id}/cancel/`), { success: "Inventário cancelado.", onSuccess: () => setCancelOpen(false) });
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <Spinner />;
  const inv = q.data;
  const editable = inv.status === "open" && can("stock.adjust");
  const items = inv.items.filter((i) => i.product_name.toLowerCase().includes(search.toLowerCase()));
  return (
    <div>
      <PageHeader back={{ to: "/estoque/inventarios", label: "Inventários" }} title={<span className="flex items-center gap-3">Inventário #{inv.id} <StatusBadge status={inv.status} label={inv.status_label} /></span>}
        description={`${inv.description || "Contagem"} · iniciado em ${dateTime(inv.started_at)} por ${inv.started_by_name}${inv.closed_at ? ` · finalizado em ${dateTime(inv.closed_at)} por ${inv.closed_by_name}` : ""}`}
        actions={editable && <>
          <Button variant="ghost" onClick={() => setCancelOpen(true)}>Cancelar</Button>
          <Button variant="secondary" loading={save.isPending} onClick={() => save.mutate(undefined)}>Salvar contagem</Button>
          <Button onClick={() => setCloseOpen(true)}>Finalizar e ajustar</Button>
        </>} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card><Stat label="Itens contados" value={`${inv.summary.counted_items} de ${inv.summary.total_items}`} /></Card>
        <Card><Stat label="Itens com diferença" value={inv.summary.items_with_difference} /></Card>
        <Card><Stat label="Diferença líquida" value={brl(inv.summary.value_difference)} tone={Number(inv.summary.value_difference) < 0 ? "bad" : "default"} /></Card>
        <Card><Stat label="Faltas valorizadas" value={brl(inv.summary.loss_value)} tone={Number(inv.summary.loss_value) < 0 ? "bad" : "default"} /></Card>
      </div>
      {inv.reason && <div className="mb-4"><Notice>Motivo do ajuste: {inv.reason}</Notice></div>}
      <Card padded={false}>
        <div className="border-b border-stone-100 p-3"><SearchInput value={search} onChange={setSearch} placeholder="Filtrar produto" className="sm:w-72" /></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-stone-200 bg-stone-50 text-left text-xs text-stone-500">
              <th className="px-4 py-2.5 font-semibold">Produto</th><th className="px-4 py-2.5 text-right font-semibold">No sistema</th>
              <th className="px-4 py-2.5 text-right font-semibold">Contado</th><th className="px-4 py-2.5 text-right font-semibold">Diferença</th>
              <th className="hidden px-4 py-2.5 text-right font-semibold md:table-cell">Valor</th><th className="hidden px-4 py-2.5 font-semibold md:table-cell">Responsável</th>
            </tr></thead>
            <tbody className="divide-y divide-stone-100">
              {items.map((i) => {
                const counted = values[i.id];
                const diff = counted === "" || counted === undefined ? null : toNum(counted.replace(",", ".")) - toNum(i.system_quantity);
                return (
                  <tr key={i.id}>
                    <td className="px-4 py-2"><div className="font-medium">{i.product_name}</div><div className="text-xs text-stone-500">{i.category_name}</div></td>
                    <td className="num px-4 py-2 text-right">{qty(i.system_quantity, i.unit_code)}</td>
                    <td className="px-4 py-2 text-right">
                      {editable ? <input inputMode="decimal" className="input ml-auto w-28 text-right" value={counted ?? ""} aria-label={`Contado de ${i.product_name}`}
                        onChange={(e) => setValues({ ...values, [i.id]: e.target.value })} /> : <span className="num">{i.counted_quantity === null ? "—" : qty(i.counted_quantity, i.unit_code)}</span>}
                    </td>
                    <td className={`num px-4 py-2 text-right font-semibold ${diff === null || diff === 0 ? "text-stone-400" : diff < 0 ? "text-red-700" : "text-green-800"}`}>
                      {diff === null ? "—" : `${diff > 0 ? "+" : ""}${qty(diff)}`}
                    </td>
                    <td className="num hidden px-4 py-2 text-right md:table-cell">{diff === null ? "—" : brl(diff * toNum(i.unit_cost))}</td>
                    <td className="hidden px-4 py-2 text-xs text-stone-500 md:table-cell">{i.counted_by_name ? `${i.counted_by_name} · ${dateTime(i.counted_at)}` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
      <ConfirmDialog open={closeOpen} onOpenChange={setCloseOpen} title="Finalizar inventário" requireReason reasonLabel="Motivo do ajuste" confirmLabel="Finalizar e ajustar" loading={close.isPending}
        description="Cada diferença vira uma movimentação de ajuste com seu nome, data e motivo. Itens não contados não são alterados." onConfirm={(r) => close.mutate(r)} />
      <ConfirmDialog open={cancelOpen} onOpenChange={setCancelOpen} title="Cancelar inventário?" danger confirmLabel="Cancelar inventário" loading={cancel.isPending}
        description="Nenhum ajuste será feito." onConfirm={() => cancel.mutate(undefined)} />
    </div>
  );
}
