import { ArrowDownRight, ArrowUpRight, Info } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { brl, date, num, pct, qty } from "@/lib/format";
import { Badge, Card, CardHeader, EmptyState, Notice, PageHeader, Spinner } from "@/components/ui";

type Change = { product: string; previous_cost: string; cost: string; unit: string; variation_percent: string; date: string };
type Data = { cost_decreases: Change[]; cost_increases: Change[];
  quote_changes: { product: string; supplier: string; previous_price: string; price: string; purchase_unit: string; variation_percent: string; quoted_at: string }[];
  competitive_suppliers: { supplier: string; best_in: number; of: number }[];
  expiring_quotes: { id: number; product_name: string; supplier_name: string; price: string; purchase_unit_code: string; valid_until: string }[];
  discount_offers: { product: string; supplier: string; discount_percent: string; product_expiry: string; days_to_expiry: number; max_useful_quantity: string; unit: string; advice: string }[];
  joint_purchase: { items: number; best_split: { total: string; suppliers: { supplier_name: string; goods_total: string; freight: string; items: { product: string }[] }[] }; best_single_supplier: { supplier_name: string; total: string } | null } | null;
  note: string };

function ChangeList({ rows, up }: { rows: Change[]; up: boolean }) {
  if (!rows.length) return <EmptyState compact title={up ? "Nenhum aumento relevante" : "Nenhuma redução relevante"} description="Variações acima de 3% nos últimos 30 dias aparecem aqui." />;
  return (
    <ul className="divide-y divide-stone-100">
      {rows.map((c) => (
        <li key={c.product + c.date} className="flex items-center justify-between gap-3 py-2.5 text-sm">
          <div><div className="font-medium">{c.product}</div><div className="text-xs text-stone-500">{brl(c.previous_cost)} → {brl(c.cost)} por {c.unit} · {date(c.date.slice(0, 10))}</div></div>
          <span className={`inline-flex items-center gap-0.5 font-semibold ${up ? "text-red-700" : "text-green-800"}`}>{up ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}{pct(Math.abs(Number(c.variation_percent)))}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Opportunities() {
  const q = useApi<Data>("/opportunities/");
  if (!q.data) return <Spinner />;
  const d = q.data;
  return (
    <div>
      <PageHeader title="Oportunidades de compra" description="Mudanças de preço, fornecedores competitivos, cotações vencendo e compras conjuntas — com base nos dados cadastrados." />
      <div className="mb-5"><Notice icon={<Info className="h-4 w-4" />}>{d.note} Não recomendamos comprar grandes quantidades apenas porque estão baratas: considere validade, consumo previsto e espaço.</Notice></div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card><CardHeader title="Aumentos recentes de custo" /><ChangeList rows={d.cost_increases} up /></Card>
        <Card><CardHeader title="Reduções de custo" /><ChangeList rows={d.cost_decreases} up={false} /></Card>
        <Card>
          <CardHeader title="Fornecedores competitivos" description="Quantas vezes cada fornecedor tem o menor custo total para repor o estoque ideal." />
          {d.competitive_suppliers.length === 0 ? <EmptyState compact title="Sem cotações suficientes" /> : (
            <ul className="space-y-2 text-sm">{d.competitive_suppliers.map((s) => <li key={s.supplier} className="flex justify-between"><span className="font-medium">{s.supplier}</span><span className="text-stone-600">melhor em {s.best_in} de {s.of} produtos</span></li>)}</ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Compra conjunta" description="Agrupar itens abaixo do mínimo por fornecedor reduz fretes e ajuda a atingir pedidos mínimos." />
          {!d.joint_purchase ? <EmptyState compact title="Nenhuma oportunidade agora" description="Aparece quando dois ou mais produtos precisam de reposição." /> : (
            <div className="space-y-2 text-sm">
              <p><strong>{d.joint_purchase.items}</strong> produtos abaixo do mínimo. Melhor combinação: <strong className="num">{brl(d.joint_purchase.best_split.total)}</strong>
                {d.joint_purchase.best_single_supplier && <> (tudo em {d.joint_purchase.best_single_supplier.supplier_name}: {brl(d.joint_purchase.best_single_supplier.total)})</>}.</p>
              <ul className="space-y-1">{d.joint_purchase.best_split.suppliers.map((s) => <li key={s.supplier_name}>• {s.supplier_name}: {s.items.map((i) => i.product).join(", ")} — {brl(s.goods_total)} + frete {brl(s.freight)}</li>)}</ul>
            </div>
          )}
        </Card>
        <Card>
          <CardHeader title="Variações entre cotações" />
          {d.quote_changes.length === 0 ? <EmptyState compact title="Sem variações relevantes" /> : (
            <ul className="divide-y divide-stone-100 text-sm">{d.quote_changes.map((c, i) => (
              <li key={i} className="flex justify-between gap-3 py-2"><span><strong>{c.product}</strong> · {c.supplier}<div className="text-xs text-stone-500">{brl(c.previous_price)} → {brl(c.price)}/{c.purchase_unit}</div></span>
                <span className={Number(c.variation_percent) > 0 ? "text-red-700" : "text-green-800"}>{pct(c.variation_percent)}</span></li>
            ))}</ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Cotações vencendo (3 dias)" />
          {d.expiring_quotes.length === 0 ? <EmptyState compact title="Nenhuma cotação vencendo" /> : (
            <ul className="divide-y divide-stone-100 text-sm">{d.expiring_quotes.map((c) => <li key={c.id} className="flex justify-between py-2"><span>{c.product_name} · {c.supplier_name}</span><span>{brl(c.price)}/{c.purchase_unit_code} até {date(c.valid_until)}</span></li>)}</ul>
          )}
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="Descontos com validade próxima" description="O limite sugerido é o consumo previsto até a validade informada pelo fornecedor." />
          {d.discount_offers.length === 0 ? <EmptyState compact title="Nenhuma oferta recente" /> : (
            <ul className="divide-y divide-stone-100 text-sm">{d.discount_offers.map((o, i) => (
              <li key={i} className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                <span><strong>{o.product}</strong> · {o.supplier} <Badge tone="pine">{num(o.discount_percent)}% off</Badge> <span className="text-xs text-stone-500">validade {date(o.product_expiry)} ({o.days_to_expiry} dias)</span></span>
                <span className="text-stone-700">{o.advice} {Number(o.max_useful_quantity) > 0 && <span className="text-xs text-stone-500">(≈ {qty(o.max_useful_quantity, o.unit)})</span>}</span>
              </li>
            ))}</ul>
          )}
        </Card>
      </div>
    </div>
  );
}
