import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { AlertTriangle, Award, Plus, Scale, Trash2 } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { brl, date, num, qty } from "@/lib/format";
import { Badge, Button, Card, CardHeader, EmptyState, Input, Notice, PageHeader, Select, useToast } from "@/components/ui";
import type { Product } from "@/components/domain/types";

type QuoteEval = { quotation_id: number; supplier_id: number; supplier_name: string; supplier_is_demo: boolean; price: string; purchase_unit: string; quoted_at: string;
  valid_until: string | null; age_days: number; stale: boolean; viable: boolean; issues: string[]; units_to_buy?: string; effective_quantity?: string; surplus?: string;
  subtotal?: string; discount?: string; freight?: string; total?: string; price_per_stock_unit?: string; delivery_days?: number; expected_delivery?: string;
  payment_terms: string; quality_rating: number | null; is_best: boolean; difference_vs_best?: string };
type ProductCmp = { product_id: number; product: string; unit: string; needed: string; best: QuoteEval | null; quotes: QuoteEval[]; note: string | null; stale_days: number };
type ListCmp = { single_supplier: { supplier_name: string; covers: number; of: number; goods_total: string; freight: string; total: string; meets_min_order: boolean; min_order_value: string }[];
  best_single_supplier: { supplier_name: string; total: string } | null;
  best_split: { total: string; suppliers: { supplier_name: string; goods_total: string; freight: string; meets_min_order: boolean; items: { product: string; units_to_buy: string; purchase_unit: string; total: string; stale: boolean }[] }[] };
  missing_quotes: { product: string }[] };

export default function Compare() {
  const [sp] = useSearchParams();
  const toast = useToast();
  const products = useApi<Page<Product>>("/products/", { page_size: 500 });
  const [lines, setLines] = useState([{ product: sp.get("produto") || "", quantity: "" }]);
  const [result, setResult] = useState<{ products: ProductCmp[]; list?: ListCmp } | null>(null);
  const [loading, setLoading] = useState(false);
  const pmap = new Map((products.data?.results || []).map((p) => [String(p.id), p]));
  useEffect(() => {
    const p = pmap.get(lines[0].product);
    if (p && !lines[0].quantity) setLines([{ product: lines[0].product, quantity: String(Math.max(Number(p.ideal_stock) - Number(p.available_quantity), Number(p.min_stock), 1)) }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [products.data]);
  const run = async () => {
    setLoading(true);
    try {
      setResult(await api.post("/compare/", { items: lines.filter((l) => l.product && l.quantity).map((l) => ({ product: Number(l.product), quantity: l.quantity.replace(",", ".") })) }));
    } catch (e) {
      toast.error(e);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div>
      <PageHeader title="Comparador de fornecedores" description="Calcula o menor custo total viável: preço padronizado, quantidade mínima, frete, descontos, disponibilidade e prazo — não apenas o menor preço anunciado." />
      <Card className="mb-5">
        <CardHeader title="O que você precisa comprar?" description="Quantidades na unidade de estoque do produto." />
        <div className="space-y-2">
          {lines.map((l, i) => (
            <div key={i} className="flex gap-2">
              <Select className="flex-1" value={l.product} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, product: e.target.value } : x)))}
                options={(products.data?.results || []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Produto" aria-label="Produto" />
              <Input className="w-32" inputMode="decimal" placeholder="Quantidade" suffix={pmap.get(l.product)?.unit_code} value={l.quantity} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} aria-label="Quantidade" />
              {lines.length > 1 && <button className="p-2 text-stone-400 hover:text-red-700" onClick={() => setLines(lines.filter((_, j) => j !== i))} aria-label="Remover"><Trash2 className="h-4 w-4" /></button>}
            </div>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setLines([...lines, { product: "", quantity: "" }])}>Adicionar produto</Button>
          <Button icon={<Scale className="h-4 w-4" />} loading={loading} disabled={!lines.some((l) => l.product && l.quantity)} onClick={run}>Comparar</Button>
        </div>
      </Card>
      {result?.list && (
        <Card className="mb-5">
          <CardHeader title="Lista completa" description="Frete contado uma vez por fornecedor. A divisão só é sugerida quando compensa o frete extra." />
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl bg-pine-50 p-4 ring-1 ring-pine-200">
              <div className="label text-pine-800">Melhor divisão entre fornecedores</div>
              <div className="num mt-1 text-2xl font-bold text-pine-950">{brl(result.list.best_split.total)}</div>
              <ul className="mt-3 space-y-2 text-sm">
                {result.list.best_split.suppliers.map((s) => (
                  <li key={s.supplier_name}><span className="font-semibold">{s.supplier_name}</span> — {brl(s.goods_total)} + frete {brl(s.freight)}
                    {!s.meets_min_order && <Badge tone="warning" className="ml-1">Abaixo do pedido mínimo</Badge>}
                    <div className="text-xs text-stone-600">{s.items.map((i) => `${num(i.units_to_buy)} ${i.purchase_unit} ${i.product}`).join(" · ")}</div></li>
                ))}
              </ul>
            </div>
            <div>
              <div className="label mb-2">Comprando tudo em um fornecedor</div>
              <ul className="divide-y divide-stone-100 text-sm">
                {result.list.single_supplier.map((s) => (
                  <li key={s.supplier_name} className="flex items-center justify-between py-2">
                    <span>{s.supplier_name} <span className="text-xs text-stone-500">({s.covers}/{s.of} itens{!s.meets_min_order ? ` · mínimo ${brl(s.min_order_value)} não atingido` : ""})</span></span>
                    <span className="num font-semibold">{brl(s.total)}</span>
                  </li>
                ))}
              </ul>
              {result.list.missing_quotes.length > 0 && <p className="mt-2 text-xs text-amber-800">Sem cotação válida: {result.list.missing_quotes.map((m) => m.product).join(", ")}</p>}
            </div>
          </div>
        </Card>
      )}
      {result?.products.map((p) => (
        <Card key={p.product_id} className="mb-5" padded={false}>
          <div className="p-5 pb-3">
            <h2 className="font-semibold">{p.product} · {qty(p.needed, p.unit)}</h2>
            {p.note && <div className="mt-2"><Notice>{p.note}</Notice></div>}
          </div>
          {p.quotes.length === 0 ? <EmptyState compact title="Nenhuma cotação cadastrada" description="Registre cotações em Compras › Cotações." /> : (
            <div className="grid gap-3 p-4 pt-0 sm:grid-cols-2 xl:grid-cols-3">
              {p.quotes.map((q) => (
                <div key={q.quotation_id} className={clsx("rounded-xl p-4 ring-1", q.is_best ? "bg-pine-50 ring-2 ring-pine-600" : q.viable ? "ring-stone-200" : "bg-stone-50 ring-stone-200 opacity-80")}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-semibold">{q.supplier_name}{q.supplier_is_demo && <span className="ml-1 text-xs font-normal text-amber-700">(fictício)</span>}</div>
                    {q.is_best ? <Badge tone="pine" icon={<Award className="h-3 w-3" />}>Menor custo total</Badge> : !q.viable ? <Badge tone="critical">Inviável</Badge> : null}
                  </div>
                  <div className="num mt-2 text-2xl font-bold">{q.total ? brl(q.total) : "—"}</div>
                  {q.difference_vs_best && <div className="text-xs text-red-700">+{brl(q.difference_vs_best)} vs. melhor</div>}
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-stone-600">
                    <dt>Preço anunciado</dt><dd className="num text-right">{brl(q.price)}/{q.purchase_unit}</dd>
                    {q.price_per_stock_unit && <><dt>Por {p.unit}</dt><dd className="num text-right">{brl(q.price_per_stock_unit)}</dd></>}
                    {q.units_to_buy && <><dt>Comprar</dt><dd className="num text-right">{num(q.units_to_buy)} {q.purchase_unit}</dd></>}
                    {q.surplus && Number(q.surplus) > 0 && <><dt>Excedente</dt><dd className="num text-right">{qty(q.surplus, p.unit)}</dd></>}
                    {q.subtotal && <><dt>Subtotal</dt><dd className="num text-right">{brl(q.subtotal)}</dd></>}
                    {q.discount && Number(q.discount) > 0 && <><dt>Desconto</dt><dd className="num text-right">−{brl(q.discount)}</dd></>}
                    {q.freight !== undefined && <><dt>Frete</dt><dd className="num text-right">{brl(q.freight)}</dd></>}
                    {q.delivery_days !== undefined && <><dt>Entrega</dt><dd className="text-right">{q.delivery_days} dia(s) · {date(q.expected_delivery)}</dd></>}
                    <dt>Pagamento</dt><dd className="text-right">{q.payment_terms || "—"}</dd>
                    <dt>Qualidade</dt><dd className="text-right">{q.quality_rating ? `${q.quality_rating}/5` : "—"}</dd>
                  </dl>
                  <div className={clsx("mt-3 text-xs", q.stale ? "font-semibold text-amber-800" : "text-stone-500")}>Cotação de {date(q.quoted_at)} ({q.age_days} dia(s)){q.valid_until ? ` · válida até ${date(q.valid_until)}` : ""}</div>
                  {q.issues.length > 0 && <ul className="mt-2 space-y-1">{q.issues.map((i) => <li key={i} className="flex gap-1 text-xs text-amber-900"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{i}</li>)}</ul>}
                </div>
              ))}
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
