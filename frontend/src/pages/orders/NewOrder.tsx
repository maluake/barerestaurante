import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";
import { api, newKey, type Page } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { brl, parseInput } from "@/lib/format";
import { Badge, Button, Card, EmptyState, Input, PageHeader, SearchInput, Select, Spinner, Textarea } from "@/components/ui";
import { ORIGINS, PAYMENTS, type MenuItem, type Order } from "@/components/domain/types";

type Line = { item: MenuItem; quantity: number; notes: string };
type Availability = { id: number; portions: string | null; limiting: string | null; note: string }[];

export default function NewOrder() {
  const nav = useNavigate();
  const items = useApi<Page<MenuItem>>("/menu-items/", { page_size: 500, is_available: true });
  const cats = useApi<{ id: number; name: string }[]>("/menu-categories/");
  const avail = useApi<Availability>("/menu-items/availability/");
  const [cat, setCat] = useState<number | "all">("all");
  const [search, setSearch] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [origin, setOrigin] = useState("table");
  const [table, setTable] = useState("");
  const [customer, setCustomer] = useState("");
  const [notes, setNotes] = useState("");
  const [discount, setDiscount] = useState("");
  const [deliveryFee, setDeliveryFee] = useState("");
  const [payment, setPayment] = useState("");
  const [key] = useState(newKey);
  const availMap = useMemo(() => new Map((avail.data || []).map((a) => [a.id, a])), [avail.data]);

  const visible = (items.data?.results || []).filter((i) => (cat === "all" || i.category === cat) && i.name.toLowerCase().includes(search.toLowerCase()));
  const add = (item: MenuItem) => setLines((ls) => {
    const ex = ls.find((l) => l.item.id === item.id);
    return ex ? ls.map((l) => (l.item.id === item.id ? { ...l, quantity: l.quantity + 1 } : l)) : [...ls, { item, quantity: 1, notes: "" }];
  });
  const setQty = (id: number, d: number) => setLines((ls) => ls.map((l) => (l.item.id === id ? { ...l, quantity: Math.max(0, l.quantity + d) } : l)).filter((l) => l.quantity > 0));
  const subtotal = lines.reduce((s, l) => s + l.quantity * Number(l.item.price), 0);
  const disc = Number(parseInput(discount)) || 0;
  const fee = Number(parseInput(deliveryFee)) || 0;
  const total = subtotal - disc + fee;

  const create = useAction(() => api.post<Order>("/orders/", {
    origin, table_label: table, customer_name: customer, notes, discount: disc.toFixed(2), delivery_fee: fee.toFixed(2),
    payment_method: payment, client_reference: key, items: lines.map((l) => ({ menu_item: l.item.id, quantity: l.quantity, notes: l.notes })),
  }), { success: (o) => `Pedido #${o.number} registrado.`, onSuccess: () => nav("/pedidos") });

  return (
    <div>
      <PageHeader title="Novo pedido" back={{ to: "/pedidos", label: "Pedidos" }} />
      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <Card padded={false}>
          <div className="space-y-3 border-b border-stone-100 p-4">
            <SearchInput value={search} onChange={setSearch} placeholder="Buscar item do cardápio" />
            <div className="flex gap-2 overflow-x-auto pb-1">
              {[{ id: "all" as const, name: "Todos" }, ...(cats.data || [])].map((c) => (
                <button key={c.id} onClick={() => setCat(c.id)} className={clsx("whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold",
                  cat === c.id ? "bg-pine-800 text-white" : "bg-stone-100 text-stone-700 hover:bg-stone-200")}>{c.name}</button>
              ))}
            </div>
          </div>
          {items.isLoading ? <Spinner /> : visible.length === 0 ? <EmptyState title="Nenhum item disponível" description="Cadastre itens no cardápio ou ajuste a busca." /> : (
            <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-3 xl:grid-cols-4">
              {visible.map((i) => {
                const a = availMap.get(i.id);
                const portions = a?.portions === null || a?.portions === undefined ? null : Number(a.portions);
                return (
                  <button key={i.id} onClick={() => add(i)} className="flex min-h-[92px] flex-col rounded-xl border border-stone-200 bg-white p-3 text-left transition hover:border-pine-400 hover:shadow-card active:scale-[0.98]">
                    <span className="line-clamp-2 text-sm font-semibold text-stone-900">{i.name}</span>
                    <span className="num mt-auto pt-2 text-sm font-bold text-pine-800">{brl(i.price)}</span>
                    {portions !== null && portions <= 5 && (
                      <span className="mt-1"><Badge tone={portions === 0 ? "critical" : "warning"}>{portions === 0 ? "Sem estoque" : `${portions} porções`}</Badge></span>
                    )}
                    {a?.note === "Sem ficha técnica" && <span className="mt-1 text-[11px] text-amber-800">Sem ficha técnica</span>}
                  </button>
                );
              })}
            </div>
          )}
        </Card>
        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card>
            <div className="grid grid-cols-2 gap-3">
              <Select label="Origem" value={origin} onChange={(e) => setOrigin(e.target.value)} options={ORIGINS} />
              {origin === "table" ? <Input label="Mesa" value={table} onChange={(e) => setTable(e.target.value)} placeholder="Ex.: 12" required />
                : <Input label="Cliente" value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="Opcional" />}
            </div>
          </Card>
          <Card padded={false}>
            <div className="flex items-center gap-2 border-b border-stone-100 px-4 py-3 text-sm font-semibold"><ShoppingBag className="h-4 w-4" /> Itens ({lines.reduce((s, l) => s + l.quantity, 0)})</div>
            {lines.length === 0 ? <p className="px-4 py-8 text-center text-sm text-stone-500">Toque nos itens para adicionar.</p> : (
              <ul className="divide-y divide-stone-100">
                {lines.map((l) => (
                  <li key={l.item.id} className="space-y-2 px-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium">{l.item.name}</span>
                      <span className="num text-sm">{brl(l.quantity * Number(l.item.price))}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button className="rounded-md border border-stone-300 p-1.5" onClick={() => setQty(l.item.id, -1)} aria-label="Diminuir"><Minus className="h-3.5 w-3.5" /></button>
                      <span className="num w-6 text-center text-sm font-semibold">{l.quantity}</span>
                      <button className="rounded-md border border-stone-300 p-1.5" onClick={() => setQty(l.item.id, 1)} aria-label="Aumentar"><Plus className="h-3.5 w-3.5" /></button>
                      <input value={l.notes} onChange={(e) => setLines((ls) => ls.map((x) => (x.item.id === l.item.id ? { ...x, notes: e.target.value } : x)))}
                        placeholder="Observação (ex.: sem cebola)" className="input h-8 flex-1 py-1 text-xs" />
                      <button className="p-1 text-stone-400 hover:text-red-700" onClick={() => setQty(l.item.id, -l.quantity)} aria-label="Remover"><Trash2 className="h-4 w-4" /></button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="space-y-3 border-t border-stone-100 p-4">
              <Textarea placeholder="Observações do pedido" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} aria-label="Observações" />
              <div className="grid grid-cols-2 gap-3">
                <Input label="Desconto (R$)" inputMode="decimal" value={discount} onChange={(e) => setDiscount(e.target.value)} placeholder="0,00" />
                {origin === "delivery" ? <Input label="Taxa de entrega" inputMode="decimal" value={deliveryFee} onChange={(e) => setDeliveryFee(e.target.value)} placeholder="0,00" />
                  : <Select label="Pagamento" value={payment} onChange={(e) => setPayment(e.target.value)} options={PAYMENTS} placeholder="Na entrega" />}
              </div>
              <div className="flex items-center justify-between pt-1">
                <span className="text-sm text-stone-500">Total</span>
                <span className="num text-2xl font-bold">{brl(total)}</span>
              </div>
              {disc > subtotal && <p className="text-xs text-red-700">O desconto não pode ser maior que o valor dos itens.</p>}
              <Button size="lg" className="w-full" disabled={!lines.length || (origin === "table" && !table) || disc > subtotal} loading={create.isPending} onClick={() => create.mutate(undefined)}>
                Registrar pedido
              </Button>
              <p className="text-center text-xs text-stone-500">O pedido entra como “Recebido”. A baixa de ingredientes acontece ao confirmar.</p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
