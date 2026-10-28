import { useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { BarChart3, Table2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { InfoTip } from "@/components/ui/InfoTip";
import { EmptyState } from "@/components/ui/States";

/** Paleta categórica validada (CVD) — atribuída em ordem fixa, nunca reciclada. */
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a"];
const GRID = "#e7e5e4";
const AXIS = "#78716c";

type Fmt = (v: number) => string;

export function ChartCard({ title, help, children, table, empty, actions, className }: {
  title: string; help?: ReactNode; children: ReactNode; table?: { columns: string[]; rows: (string | number)[][] };
  empty?: boolean; actions?: ReactNode; className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card className={className}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold text-stone-900">{title}</h3>
          {help && <InfoTip>{help}</InfoTip>}
        </div>
        <div className="flex items-center gap-1">
          {actions}
          {table && !empty && (
            <button onClick={() => setAsTable((v) => !v)} className="rounded-md p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-800"
              aria-label={asTable ? "Ver gráfico" : "Ver tabela"} title={asTable ? "Ver gráfico" : "Ver tabela"}>
              {asTable ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
            </button>
          )}
        </div>
      </div>
      {empty ? (
        <EmptyState compact title="Sem dados no período" description="Os dados aparecem aqui assim que houver registros." />
      ) : asTable && table ? (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-xs">
            <thead><tr>{table.columns.map((c) => <th key={c} className="sticky top-0 bg-white px-2 py-1.5 text-left font-semibold text-stone-500">{c}</th>)}</tr></thead>
            <tbody className="divide-y divide-stone-100">
              {table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={`px-2 py-1.5 ${j > 0 ? "num text-right" : ""}`}>{v}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
    </Card>
  );
}

function TooltipBox({ active, payload, label, fmt, labelFmt }: {
  active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; fmt: Fmt; labelFmt?: (l: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg bg-white px-3 py-2 text-xs shadow-pop">
      <div className="mb-1 font-semibold text-stone-900">{labelFmt ? labelFmt(String(label)) : label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 text-stone-700">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} aria-hidden />
          <span>{p.name}</span>
          <span className="num ml-auto pl-3 font-semibold text-stone-900">{fmt(Number(p.value))}</span>
        </div>
      ))}
    </div>
  );
}

export type SeriesDef = { key: string; name: string };

export function TimeBars({ data, xKey, series, fmt, axisFmt, xFmt, height = 240 }: {
  data: Record<string, unknown>[]; xKey: string; series: SeriesDef[]; fmt: Fmt; axisFmt?: Fmt; xFmt?: (v: string) => string; height?: number;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barGap={2}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey={xKey} tickFormatter={xFmt} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={12} />
          <YAxis tickFormatter={axisFmt || fmt} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} width={64} />
          <Tooltip cursor={{ fill: "rgba(120,113,108,0.08)" }} content={<TooltipBox fmt={fmt} labelFmt={xFmt} />} />
          {series.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "#44403c" }} />}
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={SERIES[i]} radius={[4, 4, 0, 0]} maxBarSize={28} stroke="#fff" strokeWidth={1} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TimeLines({ data, xKey, series, fmt, axisFmt, xFmt, height = 240 }: {
  data: Record<string, unknown>[]; xKey: string; series: SeriesDef[]; fmt: Fmt; axisFmt?: Fmt; xFmt?: (v: string) => string; height?: number;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey={xKey} tickFormatter={xFmt} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={16} />
          <YAxis tickFormatter={axisFmt || fmt} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} width={64} domain={["auto", "auto"]} />
          <Tooltip cursor={{ stroke: "#a8a29e", strokeDasharray: "3 3" }} content={<TooltipBox fmt={fmt} labelFmt={xFmt} />} />
          {series.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "#44403c" }} />}
          {series.map((s, i) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={SERIES[i % SERIES.length]} strokeWidth={2}
              dot={false} activeDot={{ r: 4, stroke: "#fff", strokeWidth: 2 }} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Barras horizontais com rótulo do item à esquerda e valor ao final (ranking). */
export function RankBars({ data, labelKey, valueKey, fmt, color = SERIES[0], valueLabel }: {
  data: Record<string, unknown>[]; labelKey: string; valueKey: string; fmt: Fmt; color?: string; valueLabel: string;
}) {
  const max = Math.max(...data.map((d) => Number(d[valueKey]) || 0), 1);
  return (
    <ul className="space-y-2.5" aria-label={valueLabel}>
      {data.map((d, i) => {
        const v = Number(d[valueKey]) || 0;
        return (
          <li key={i} className="group" title={`${d[labelKey]}: ${fmt(v)}`}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
              <span className="truncate font-medium text-stone-700">{String(d[labelKey] ?? "—")}</span>
              <span className="num shrink-0 font-semibold text-stone-900">{fmt(v)}</span>
            </div>
            <div className="h-2 rounded-full bg-stone-100">
              <div className="h-2 rounded-full transition-all group-hover:opacity-80" style={{ width: `${Math.max((v / max) * 100, 1.5)}%`, background: color }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function CategoryBars({ data, labelKey, valueKey, fmt, height = 220 }: {
  data: Record<string, unknown>[]; labelKey: string; valueKey: string; fmt: Fmt; height?: number;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 11, fill: AXIS }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey={labelKey} tick={{ fontSize: 11, fill: "#44403c" }} tickLine={false} axisLine={false} width={120} />
          <Tooltip cursor={{ fill: "rgba(120,113,108,0.08)" }} content={<TooltipBox fmt={fmt} />} />
          <Bar dataKey={valueKey} name="Valor" radius={[0, 4, 4, 0]} maxBarSize={18}>
            {data.map((_, i) => <Cell key={i} fill={SERIES[0]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
