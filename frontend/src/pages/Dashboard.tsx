import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, CheckCircle2, ChevronRight, Minus } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, brlCompact, dateShort, int, num, toNum } from "@/lib/format";
import { Card, CardHeader, EmptyState, ErrorState, InfoTip, PageHeader, Segmented, Skeleton } from "@/components/ui";
import { ChartCard, RankBars, TimeBars, TimeLines, CategoryBars, SERIES } from "@/components/charts/Charts";
import { AlertItem, type Alert } from "@/components/domain/AlertItem";

type Kpi = { key: string; label: string; value: string | number; format: "money" | "int"; previous: string | number | null;
  change_percent: string | null; compare_label: string; help: string; link: string };
type Series = { period: string; net: string; gross: string; cogs: string; count: number }[];
type DashboardData = {
  today: string; scope: string; units: string[]; kpis: Kpi[]; attention: Alert[]; attention_total: number;
  charts: {
    sales_daily: Series; sales_weekly: Series; sales_monthly: Series;
    purchases_weekly: { period: string; value: string }[];
    cost_evolution: Record<string, { date: string; cost: string }[]>;
    top_sold: { item: string; quantity: string; revenue: string }[];
    top_margin: { item: string; contribution_margin: string; margin_percent: string }[];
    waste_weekly: { period: string; value: string }[];
    waste_by_category: { product__category__name: string | null; value: string }[];
    stock_value: { date: string; value: string }[];
    supplier_performance: { supplier: string; orders: number; received_value: string; on_time_rate: number | null; fill_rate: number | null; issues: number }[];
  };
};

// Indicadores em que subir é ruim
const COST_LIKE = new Set(["cogs_month", "waste_month"]);
const PRIMARY = ["revenue_today", "orders_today", "avg_ticket", "open_orders"];

function KpiCard({ k, big }: { k: Kpi; big?: boolean }) {
  const nav = useNavigate();
  const change = k.change_percent === null ? null : toNum(k.change_percent);
  const good = change === null ? null : COST_LIKE.has(k.key) ? change < 0 : change > 0;
  const value = k.format === "money" ? (big ? brl(k.value) : brlCompact(k.value)) : int(k.value);
  return (
    <button onClick={() => k.link && nav(k.link)} className={clsx("card group flex w-full flex-col text-left transition-shadow hover:shadow-pop", big ? "p-5" : "p-4")}>
      <div className="flex items-center gap-1 text-xs font-medium text-stone-500">
        <span className="truncate">{k.label}</span>
        <span onClick={(e) => e.stopPropagation()}><InfoTip>{k.help}</InfoTip></span>
        <ChevronRight className="ml-auto h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
      <div className={clsx("num mt-1.5 font-bold tracking-tight text-stone-900", big ? "text-2xl sm:text-3xl" : "text-xl")}>{value}</div>
      {k.previous !== null && (
        <div className="mt-1.5 flex items-center gap-1 text-xs" title={k.compare_label}>
          {change === null ? (
            <span className="text-stone-400">sem base de comparação</span>
          ) : (
            <>
              <span className={clsx("inline-flex items-center gap-0.5 font-semibold", change === 0 ? "text-stone-500" : good ? "text-green-800" : "text-red-700")}>
                {change > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : change < 0 ? <ArrowDownRight className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
                {num(Math.abs(change), 1)}%
              </span>
              <span className="truncate text-stone-400">{k.compare_label.replace(/\(.*\)/, "").trim()}</span>
            </>
          )}
        </div>
      )}
    </button>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
      <div className="grid gap-4 lg:grid-cols-3"><Skeleton className="h-72 lg:col-span-2" /><Skeleton className="h-72" /></div>
    </div>
  );
}

export default function Dashboard() {
  const { units, can } = useAuth();
  const [scope, setScope] = useState<"unit" | "all">("unit");
  const [grain, setGrain] = useState<"day" | "week" | "month">("day");
  const q = useApi<DashboardData>("/dashboard/", { scope: scope === "all" ? "all" : undefined }, { refetchInterval: 60_000 });
  const d = q.data;

  const salesData = useMemo(() => {
    const src = d ? (grain === "day" ? d.charts.sales_daily : grain === "week" ? d.charts.sales_weekly : d.charts.sales_monthly) : [];
    return src.map((r) => ({ period: r.period, Líquido: toNum(r.net), CMV: toNum(r.cogs) }));
  }, [d, grain]);
  const xFmt = (v: string) => grain === "month" ? new Date(v + "T12:00").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }) : dateShort(v);

  // Evolução de custos indexada (base 100) para comparar insumos de preços muito diferentes no mesmo eixo.
  const costIdx = useMemo(() => {
    if (!d) return { rows: [], names: [] as string[] };
    const names = Object.keys(d.charts.cost_evolution).slice(0, 3);
    const byDate: Record<string, Record<string, number | string>> = {};
    names.forEach((n) => {
      const pts = d.charts.cost_evolution[n];
      const base = toNum(pts[0]?.cost) || 1;
      pts.forEach((p) => { (byDate[p.date] ||= { date: p.date })[n] = Math.round((toNum(p.cost) / base) * 1000) / 10; });
    });
    return { rows: Object.values(byDate).sort((a, b) => String(a.date).localeCompare(String(b.date))), names };
  }, [d]);

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const kpi = (key: string) => d?.kpis.find((k) => k.key === key);
  const secondary = d?.kpis.filter((k) => !PRIMARY.includes(k.key)) || [];

  return (
    <div>
      <PageHeader
        title="Visão geral"
        description={d ? `Dados de ${d.units.join(", ")} · atualizado automaticamente` : "Centro de comando do negócio"}
        actions={units.length > 1 && can("dashboard.view") ? (
          <Segmented value={scope} onChange={setScope} items={[{ value: "unit", label: "Unidade atual" }, { value: "all", label: "Consolidado" }]} />
        ) : undefined}
      />
      {!d ? <DashboardSkeleton /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {PRIMARY.map((k) => kpi(k) && <KpiCard key={k} k={kpi(k)!} big />)}
          </div>

          <div className="grid gap-5 xl:grid-cols-3">
            <Card className="xl:col-span-1 xl:row-span-2">
              <CardHeader title="Atenção hoje" description={d.attention_total ? `${d.attention_total} alerta(s) em aberto, por prioridade` : undefined}
                actions={<Link to="/alertas" className="link text-sm">Ver todos</Link>} />
              {d.attention.length === 0 ? (
                <EmptyState compact icon={<CheckCircle2 className="h-6 w-6 text-green-700" />} title="Tudo sob controle" description="Nenhum alerta prioritário no momento." />
              ) : (
                <div className="-my-2 divide-y divide-stone-100">{d.attention.map((a) => <AlertItem key={a.id} alert={a} compact />)}</div>
              )}
            </Card>
            <ChartCard className="xl:col-span-2" title="Vendas e CMV"
              help="Receita líquida das vendas concluídas e o custo real dos ingredientes consumidos (CMV) no mesmo período. A diferença é a margem de contribuição."
              actions={<Segmented value={grain} onChange={setGrain} items={[{ value: "day", label: "Dia" }, { value: "week", label: "Semana" }, { value: "month", label: "Mês" }]} />}
              empty={!salesData.some((r) => r.Líquido > 0)}
              table={{ columns: ["Período", "Líquido", "CMV"], rows: salesData.map((r) => [xFmt(r.period), brl(r.Líquido), brl(r.CMV)]) }}>
              <TimeBars data={salesData} xKey="period" xFmt={xFmt} fmt={brl} axisFmt={brlCompact}
                series={[{ key: "Líquido", name: "Receita líquida" }, { key: "CMV", name: "CMV" }]} />
            </ChartCard>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:col-span-2">
              {secondary.map((k) => <KpiCard key={k.key} k={k} />)}
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
            <ChartCard title="Mais vendidos (30 dias)" help="Itens do cardápio por quantidade vendida nos últimos 30 dias."
              empty={!d.charts.top_sold.length} table={{ columns: ["Item", "Qtd.", "Receita"], rows: d.charts.top_sold.map((r) => [r.item, num(r.quantity), brl(r.revenue)]) }}>
              <RankBars data={d.charts.top_sold} labelKey="item" valueKey="quantity" fmt={(v) => `${num(v)} un`} valueLabel="Quantidade vendida" />
            </ChartCard>
            <ChartCard title="Maior margem de contribuição (30 dias)" help="Receita do item menos o custo teórico da ficha técnica, somado no período. Itens sem ficha técnica não aparecem."
              empty={!d.charts.top_margin.length} table={{ columns: ["Item", "Margem", "Margem %"], rows: d.charts.top_margin.map((r) => [r.item, brl(r.contribution_margin), `${num(r.margin_percent, 1)}%`]) }}>
              <RankBars data={d.charts.top_margin} labelKey="item" valueKey="contribution_margin" fmt={brl} color={SERIES[2]} valueLabel="Margem de contribuição" />
            </ChartCard>
            <ChartCard title="Evolução do valor em estoque" help="Valor do estoque reconstruído dia a dia a partir das movimentações (entradas somam, saídas subtraem)."
              empty={!d.charts.stock_value.length} table={{ columns: ["Data", "Valor"], rows: d.charts.stock_value.map((r) => [dateShort(r.date), brl(r.value)]) }}>
              <TimeLines data={d.charts.stock_value.map((r) => ({ date: r.date, Valor: toNum(r.value) }))} xKey="date" xFmt={dateShort} fmt={brl} axisFmt={brlCompact} series={[{ key: "Valor", name: "Valor em estoque" }]} height={220} />
            </ChartCard>
            <ChartCard title="Compras recebidas por semana" help="Valor dos recebimentos de mercadorias registrados, por semana."
              empty={!d.charts.purchases_weekly.length} table={{ columns: ["Semana", "Valor"], rows: d.charts.purchases_weekly.map((r) => [dateShort(r.period), brl(r.value)]) }}>
              <TimeBars data={d.charts.purchases_weekly.map((r) => ({ period: r.period, Compras: toNum(r.value) }))} xKey="period" xFmt={dateShort} fmt={brl} axisFmt={brlCompact} series={[{ key: "Compras", name: "Compras" }]} height={220} />
            </ChartCard>
            <ChartCard title="Custo dos principais insumos (índice)" help="Variação do custo de reposição dos 3 insumos de maior consumo, com base 100 na primeira compra dos últimos 90 dias. Acima de 100 = mais caro."
              empty={!costIdx.rows.length} table={{ columns: ["Data", ...costIdx.names], rows: costIdx.rows.map((r) => [dateShort(String(r.date)), ...costIdx.names.map((n) => (r[n] === undefined ? "—" : num(r[n], 1)))]) }}>
              <TimeLines data={costIdx.rows} xKey="date" xFmt={dateShort} fmt={(v) => num(v, 1)} series={costIdx.names.map((n) => ({ key: n, name: n }))} height={220} />
            </ChartCard>
            <ChartCard title="Perdas e desperdício por semana" help="Custo das perdas e descartes registrados, por semana (últimas 12 semanas)."
              empty={!d.charts.waste_weekly.length} table={{ columns: ["Semana", "Valor"], rows: d.charts.waste_weekly.map((r) => [dateShort(r.period), brl(r.value)]) }}>
              <TimeBars data={d.charts.waste_weekly.map((r) => ({ period: r.period, Perdas: toNum(r.value) }))} xKey="period" xFmt={dateShort} fmt={brl} axisFmt={brlCompact} series={[{ key: "Perdas", name: "Perdas" }]} height={220} />
            </ChartCard>
            <ChartCard title="Desperdício por categoria (mês)" help="Custo das perdas do mês agrupado pela categoria do produto."
              empty={!d.charts.waste_by_category.length} table={{ columns: ["Categoria", "Valor"], rows: d.charts.waste_by_category.map((r) => [r.product__category__name || "Sem categoria", brl(r.value)]) }}>
              <CategoryBars data={d.charts.waste_by_category.map((r) => ({ name: r.product__category__name || "Sem categoria", value: toNum(r.value) }))} labelKey="name" valueKey="value" fmt={brlCompact} />
            </ChartCard>
            <Card className="lg:col-span-2">
              <CardHeader title="Desempenho dos fornecedores (90 dias)" description="Pontualidade = entregas até a data prevista. Atendimento = recebido ÷ pedido." actions={<Link to="/relatorios?r=supplier_performance" className="link text-sm">Relatório</Link>} />
              {d.charts.supplier_performance.length === 0 ? <EmptyState compact title="Sem compras no período" /> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-xs text-stone-500"><th className="py-2 pr-3 font-semibold">Fornecedor</th><th className="py-2 pr-3 text-right font-semibold">Pedidos</th><th className="py-2 pr-3 text-right font-semibold">Recebido</th><th className="py-2 pr-3 text-right font-semibold">Pontualidade</th><th className="py-2 pr-3 text-right font-semibold">Atendimento</th><th className="py-2 text-right font-semibold">Ocorrências</th></tr></thead>
                    <tbody className="divide-y divide-stone-100">
                      {d.charts.supplier_performance.map((s) => (
                        <tr key={s.supplier}>
                          <td className="py-2 pr-3 font-medium">{s.supplier}</td>
                          <td className="num py-2 pr-3 text-right">{s.orders}</td>
                          <td className="num py-2 pr-3 text-right">{brl(s.received_value)}</td>
                          <td className="num py-2 pr-3 text-right">{s.on_time_rate === null ? "—" : `${num(s.on_time_rate, 1)}%`}</td>
                          <td className="num py-2 pr-3 text-right">{s.fill_rate === null ? "—" : `${num(s.fill_rate, 1)}%`}</td>
                          <td className="num py-2 text-right">{s.issues}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
