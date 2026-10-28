import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { Download, Printer } from "lucide-react";
import { downloadFile } from "@/lib/api";
import { useApi, useOptions } from "@/lib/hooks";
import { useToast } from "@/components/ui/Toast";
import { brl, date, dateTime, monthStartISO, num, pct, todayISO } from "@/lib/format";
import { Button, Card, EmptyState, ErrorState, Input, PageHeader, Select, Spinner } from "@/components/ui";

type Col = { key: string; label: string; type: string };
type Report = { key: string; title: string; description: string; columns: Col[]; rows: Record<string, unknown>[]; totals: Record<string, unknown> | null; start: string; end: string; units: string[] };
type Meta = { key: string; title: string; description: string; finance: boolean };

const GROUPS: Record<string, string[]> = {
  Vendas: ["sales_by_period", "ticket", "top_items", "period_comparison", "prep_time"],
  "Custos e margens": ["margin_items", "menu_costs", "cogs", "cost_evolution", "consumption_variance"],
  Estoque: ["waste", "expiring", "stagnant", "inventory_differences", "sustainability"],
  Compras: ["supplier_performance", "purchase_history", "planned_vs_actual"],
};
const TOTAL_LABELS: Record<string, string> = { value: "Valor", net: "Líquido", gross: "Bruto", cogs: "CMV", margin: "Margem", count: "Vendas", ticket: "Ticket médio",
  total: "Total", received: "Recebido", net_revenue: "Receita líquida", cogs_percent: "CMV %", orders: "Pedidos" };

function cell(v: unknown, type: string, row: Record<string, unknown>) {
  if (v === null || v === undefined || v === "") return "—";
  const t = type === "auto" ? String(row.type || "text") : type;
  if (t === "money") return brl(v);
  if (t === "money4") return `R$ ${num(v, 4)}`;
  if (t === "percent") return pct(v);
  if (t === "int" || t === "number") return num(v);
  if (t === "date") return date(String(v));
  if (t === "datetime") return dateTime(String(v));
  return String(v);
}

export default function Reports() {
  const [sp, setSp] = useSearchParams();
  const toast = useToast();
  const list = useApi<Meta[]>("/reports/");
  const key = sp.get("r") || "sales_by_period";
  const [start, setStart] = useState(monthStartISO());
  const [end, setEnd] = useState(todayISO());
  const [category, setCategory] = useState("");
  const [product, setProduct] = useState("");
  const [supplier, setSupplier] = useState("");
  const [group, setGroup] = useState("category");
  const cats = useOptions("/categories/");
  const prods = useOptions("/products/");
  const sups = useOptions("/suppliers/");
  const params = { start, end, category: category || undefined, product: product || undefined, supplier: supplier || undefined, group: key === "waste" ? group : undefined };
  const available = new Set((list.data || []).map((r) => r.key));
  const q = useApi<Report>(available.has(key) ? `/reports/${key}/` : null, params);
  const exportCsv = () => downloadFile(`/reports/${key}/`, { ...params, export: "csv" }, `${key}_${start}_${end}.csv`).catch((e) => toast.error(e));
  const r = q.data;
  return (
    <div>
      <PageHeader title="Relatórios" description="Dados reais, fórmulas explicadas e exportação em CSV. Use “Imprimir / PDF” para gerar um documento para análise." />
      <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
        <nav className="space-y-4 print:hidden" aria-label="Relatórios">
          {Object.entries(GROUPS).map(([g, keys]) => {
            const items = keys.filter((k) => available.has(k));
            if (!items.length) return null;
            return (
              <div key={g}>
                <div className="label mb-1 px-2">{g}</div>
                {items.map((k) => {
                  const m = list.data!.find((x) => x.key === k)!;
                  return <button key={k} onClick={() => setSp({ r: k })} className={clsx("block w-full rounded-lg px-2 py-1.5 text-left text-sm", k === key ? "bg-pine-100 font-semibold text-pine-900" : "text-stone-700 hover:bg-stone-100")}>{m.title}</button>;
                })}
              </div>
            );
          })}
        </nav>
        <div className="min-w-0">
          <Card className="mb-4 print:hidden">
            <div className="flex flex-wrap items-end gap-3">
              <Input label="De" type="date" className="w-40" value={start} onChange={(e) => setStart(e.target.value)} />
              <Input label="Até" type="date" className="w-40" value={end} onChange={(e) => setEnd(e.target.value)} />
              {["waste", "cost_evolution"].includes(key) && <Select label="Categoria" className="w-48" value={category} onChange={(e) => setCategory(e.target.value)} options={cats.options} placeholder="Todas" />}
              {["waste", "cost_evolution"].includes(key) && <Select label="Produto" className="w-48" value={product} onChange={(e) => setProduct(e.target.value)} options={prods.options} placeholder="Todos" />}
              {key === "purchase_history" && <Select label="Fornecedor" className="w-48" value={supplier} onChange={(e) => setSupplier(e.target.value)} options={sups.options} placeholder="Todos" />}
              {key === "waste" && <Select label="Agrupar por" className="w-40" value={group} onChange={(e) => setGroup(e.target.value)}
                options={[{ value: "category", label: "Categoria" }, { value: "product", label: "Produto" }, { value: "reason", label: "Motivo" }, { value: "unit", label: "Unidade" }, { value: "detail", label: "Detalhado" }]} />}
              <div className="ml-auto flex gap-2">
                <Button variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportCsv} disabled={!r}>CSV</Button>
                <Button variant="secondary" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()} disabled={!r}>Imprimir / PDF</Button>
              </div>
            </div>
          </Card>
          {q.error ? <ErrorState error={q.error} /> : !r ? <Spinner /> : (
            <Card padded={false}>
              <div className="border-b border-stone-100 p-5">
                <h2 className="text-lg font-bold">{r.title}</h2>
                <p className="mt-1 text-sm text-stone-600">{r.description}</p>
                <p className="mt-1 text-xs text-stone-500">Período: {date(r.start)} a {date(r.end)} · {r.units.join(", ")}</p>
              </div>
              {r.totals && (
                <div className="flex flex-wrap gap-6 border-b border-stone-100 px-5 py-3">
                  {Object.entries(r.totals).map(([k, v]) => <div key={k}><div className="text-xs text-stone-500">{TOTAL_LABELS[k] || k}</div><div className="num font-semibold">{k.includes("percent") ? pct(v) : ["count", "orders"].includes(k) ? num(v) : k === "total" && key === "prep_time" ? `${num(v)} min` : brl(v)}</div></div>)}
                </div>
              )}
              {r.rows.length === 0 ? <EmptyState title="Sem dados no período" description="Ajuste as datas ou filtros." /> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b border-stone-200 bg-stone-50">{r.columns.map((c) => <th key={c.key} className={clsx("whitespace-nowrap px-4 py-2.5 text-xs font-semibold text-stone-500", ["money", "money4", "percent", "int", "number", "auto"].includes(c.type) ? "text-right" : "text-left")}>{c.label}</th>)}</tr></thead>
                    <tbody className="divide-y divide-stone-100">
                      {r.rows.map((row, i) => (
                        <tr key={i}>{r.columns.map((c) => <td key={c.key} className={clsx("px-4 py-2", ["money", "money4", "percent", "int", "number", "auto"].includes(c.type) && "num text-right")}>{cell(row[c.key], c.type, row)}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
