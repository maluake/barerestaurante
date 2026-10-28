import { useState } from "react";
import { AlertTriangle, Plus } from "lucide-react";
import { api, type Page } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, brlCompact, date, dateShort, dateTime, monthStartISO, pct, todayISO, toNum } from "@/lib/format";
import {
  Badge, Button, Card, CardHeader, ConfirmDialog, DataTable, EmptyState, FormGrid, InfoTip, Input, Modal, Notice, PageHeader, Pagination, Segmented,
  Select, Spinner, Stat, StatusBadge, Tabs, Textarea, Toolbar,
} from "@/components/ui";
import { ChartCard, TimeBars, TimeLines } from "@/components/charts/Charts";

type Summary = { sales_count: number; gross: string; discounts: string; fees: string; delivery_fees: string; net: string; cogs: string; cancelled_value: string;
  average_ticket: string; contribution_margin: string; contribution_margin_percent: string | null; cogs_percent: string | null; registered_expenses: string;
  merchandise_purchases: string; other_income: string; waste_value: string; operating_result_estimate: string; limitations: string[]; disclaimer: string;
  expenses_by_category: { category: string; kind: string; value: string }[];
  previous: Record<string, string | number> };
type Flow = { series: { date: string; inflow: string; outflow: string; net: string; cumulative: string }[]; upcoming_payables: string; upcoming_receivables: string; overdue_payables: string; note: string };
type Entry = { id: number; kind: string; category: number; category_name: string; category_kind: string; description: string; amount: string; competence_date: string; due_date: string;
  status: string; status_label: string; paid_at: string | null; paid_amount: string | null; supplier_name: string | null; purchase_order_number: number | null; is_overdue: boolean; document: string };
type Cash = { id: number; status: string; opened_by_name: string; opened_at: string; opening_amount: string; closed_by_name: string | null; closed_at: string | null;
  expected_amount: string | null; counted_amount: string | null; difference: string | null; notes: string;
  movements: { id: number; kind_label: string; amount: string; reason: string; user_name: string; created_at: string }[];
  breakdown: { opening: string; cash_sales: string; supplies: string; withdrawals: string; expected: string } };

function Line({ label, value, strong, neg, help }: { label: string; value: string; strong?: boolean; neg?: boolean; help?: string }) {
  return (
    <div className={`flex items-center justify-between py-1.5 text-sm ${strong ? "border-t border-stone-200 pt-2.5 font-semibold" : ""}`}>
      <span className="flex items-center gap-1 text-stone-700">{label}{help && <InfoTip>{help}</InfoTip>}</span>
      <span className={`num ${neg ? "text-red-700" : ""}`}>{neg ? "−" : ""}{value}</span>
    </div>
  );
}

function SummaryTab({ start, end, scope }: { start: string; end: string; scope: string }) {
  const q = useApi<Summary>("/finance/summary/", { start, end, scope: scope === "all" ? "all" : undefined });
  const f = useApi<Flow>("/finance/cash-flow/", { start, end, scope: scope === "all" ? "all" : undefined });
  if (!q.data) return <Spinner />;
  const s = q.data;
  const change = (k: string) => { const p = toNum(s.previous[k]); return p ? ((toNum((s as unknown as Record<string, string>)[k]) - p) / Math.abs(p)) * 100 : null; };
  return (
    <div className="space-y-5">
      <Notice tone="warning" icon={<AlertTriangle className="h-4 w-4" />} title="Faturamento não é lucro">{s.disclaimer}</Notice>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {([["net", "Receita líquida"], ["cogs", "CMV"], ["contribution_margin", "Margem de contribuição"], ["operating_result_estimate", "Resultado operacional estimado"]] as const).map(([k, l]) => {
          const c = change(k);
          return <Card key={k}><Stat label={l} value={brl((s as unknown as Record<string, string>)[k])} tone={k === "operating_result_estimate" && toNum(s[k]) < 0 ? "bad" : "default"}
            hint={c === null ? "sem período anterior" : `${c >= 0 ? "+" : ""}${pct(c)} vs. período anterior`} /></Card>;
        })}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Demonstrativo do período" description={`${s.sales_count} vendas · ticket médio ${brl(s.average_ticket)}`} />
          <Line label="Faturamento bruto" value={brl(s.gross)} help="Soma de quantidade × preço dos itens vendidos (vendas concluídas)." />
          <Line label="Descontos" value={brl(s.discounts)} neg />
          <Line label="Taxas de plataforma/cartão" value={brl(s.fees)} neg />
          <Line label="Taxas de entrega cobradas" value={brl(s.delivery_fees)} />
          <Line label="Receita líquida" value={brl(s.net)} strong />
          <Line label={`CMV ${s.cogs_percent ? `(${pct(s.cogs_percent)} da receita)` : ""}`} value={brl(s.cogs)} neg help="Custo real dos lotes de ingredientes consumidos pelas vendas." />
          <Line label={`Margem de contribuição ${s.contribution_margin_percent ? `(${pct(s.contribution_margin_percent)})` : ""}`} value={brl(s.contribution_margin)} strong />
          <Line label="Outras receitas registradas" value={brl(s.other_income)} />
          <Line label="Despesas registradas (exceto mercadorias)" value={brl(s.registered_expenses)} neg />
          <Line label="Resultado operacional estimado" value={brl(s.operating_result_estimate)} strong />
          <div className="mt-3 space-y-1 text-xs text-stone-500">
            <p>Compras de mercadorias no período: {brl(s.merchandise_purchases)} (não somadas ao resultado — entram pelo CMV quando consumidas).</p>
            <p>Desperdício registrado: {brl(s.waste_value)} · Vendas canceladas: {brl(s.cancelled_value)}</p>
          </div>
        </Card>
        <Card>
          <CardHeader title="Limitações deste resultado" />
          {s.limitations.length === 0 ? <p className="text-sm text-stone-600">Sem limitações detectadas para o período.</p> : (
            <ul className="space-y-2">{s.limitations.map((l) => <li key={l} className="flex gap-2 text-sm text-stone-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />{l}</li>)}</ul>
          )}
          <h3 className="mb-2 mt-6 text-sm font-semibold">Despesas por categoria</h3>
          {s.expenses_by_category.length === 0 ? <p className="text-sm text-stone-500">Nenhuma despesa registrada.</p> : (
            <ul className="divide-y divide-stone-100 text-sm">{s.expenses_by_category.map((e) => <li key={e.category} className="flex justify-between py-1.5"><span>{e.category}</span><span className="num">{brl(e.value)}</span></li>)}</ul>
          )}
        </Card>
      </div>
      {f.data && (
        <div className="grid gap-5 lg:grid-cols-3">
          <ChartCard className="lg:col-span-2" title="Fluxo de caixa diário" help={f.data.note}
            empty={!f.data.series.some((r) => toNum(r.inflow) || toNum(r.outflow))}
            table={{ columns: ["Data", "Entradas", "Saídas", "Saldo"], rows: f.data.series.map((r) => [dateShort(r.date), brl(r.inflow), brl(r.outflow), brl(r.net)]) }}>
            <TimeBars data={f.data.series.map((r) => ({ date: r.date, Entradas: toNum(r.inflow), Saídas: toNum(r.outflow) }))} xKey="date" xFmt={dateShort} fmt={brl} axisFmt={brlCompact}
              series={[{ key: "Entradas", name: "Entradas" }, { key: "Saídas", name: "Saídas" }]} />
          </ChartCard>
          <ChartCard title="Saldo acumulado" table={{ columns: ["Data", "Acumulado"], rows: f.data.series.map((r) => [dateShort(r.date), brl(r.cumulative)]) }}>
            <TimeLines data={f.data.series.map((r) => ({ date: r.date, Acumulado: toNum(r.cumulative) }))} xKey="date" xFmt={dateShort} fmt={brl} axisFmt={brlCompact} series={[{ key: "Acumulado", name: "Acumulado" }]} height={180} />
            <div className="mt-3 space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-stone-500">A pagar (30 dias)</span><span className="num">{brl(f.data.upcoming_payables)}</span></div>
              <div className="flex justify-between"><span className="text-stone-500">A receber (30 dias)</span><span className="num">{brl(f.data.upcoming_receivables)}</span></div>
              <div className="flex justify-between"><span className="text-stone-500">Contas vencidas</span><span className="num text-red-700">{brl(f.data.overdue_payables)}</span></div>
            </div>
          </ChartCard>
        </div>
      )}
    </div>
  );
}

function EntryForm({ onDone }: { onDone: () => void }) {
  const cats = useApi<{ id: number; name: string; kind: string }[]>("/expense-categories/");
  const [f, setF] = useState({ kind: "payable", category: "", description: "", amount: "", competence_date: todayISO(), due_date: todayISO(), document: "", notes: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const save = useAction(() => api.post("/financial-entries/", { ...f, category: Number(f.category), amount: f.amount.replace(",", ".") }), { success: "Lançamento registrado.", onSuccess: onDone });
  return (
    <div className="space-y-4">
      <FormGrid>
        <Select label="Tipo" value={f.kind} onChange={set("kind")} options={[{ value: "payable", label: "Conta a pagar" }, { value: "receivable", label: "Conta a receber" }]} />
        <Select label="Categoria" value={f.category} onChange={set("category")} options={(cats.data || []).map((c) => ({ value: c.id, label: c.name }))} placeholder="Selecione" />
      </FormGrid>
      <Input label="Descrição" value={f.description} onChange={set("description")} required />
      <FormGrid cols={3}>
        <Input label="Valor (R$)" inputMode="decimal" value={f.amount} onChange={set("amount")} required />
        <Input label="Competência" type="date" value={f.competence_date} onChange={set("competence_date")} />
        <Input label="Vencimento" type="date" value={f.due_date} onChange={set("due_date")} />
      </FormGrid>
      <Input label="Documento" value={f.document} onChange={set("document")} />
      <Textarea label="Observações" value={f.notes} onChange={set("notes")} />
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!f.category || !f.description || !f.amount} onClick={() => save.mutate(undefined)}>Salvar</Button></div>
    </div>
  );
}

function EntriesTab() {
  const { can } = useAuth();
  const [kind, setKind] = useState("payable");
  const [status, setStatus] = useState("open");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [pay, setPay] = useState<Entry | null>(null);
  const [cancel, setCancel] = useState<Entry | null>(null);
  const [payDate, setPayDate] = useState(todayISO());
  const q = useApi<Page<Entry>>("/financial-entries/", { kind, status: status || undefined, page, ordering: "due_date" });
  const doPay = useAction(() => api.post(`/financial-entries/${pay!.id}/pay/`, { paid_at: payDate }), { success: "Pagamento registrado.", onSuccess: () => setPay(null) });
  const doCancel = useAction((reason: string) => api.post(`/financial-entries/${cancel!.id}/cancel/`, { reason }), { success: "Lançamento cancelado.", onSuccess: () => setCancel(null) });
  const reopen = useAction((id: number) => api.post(`/financial-entries/${id}/reopen/`), { success: "Pagamento estornado." });
  return (
    <>
      <Toolbar>
        <Segmented value={kind} onChange={(v) => { setKind(v); setPage(1); }} items={[{ value: "payable", label: "A pagar" }, { value: "receivable", label: "A receber" }]} />
        <Select className="sm:w-44" value={status} onChange={(e) => setStatus(e.target.value)} options={[{ value: "open", label: "Em aberto" }, { value: "paid", label: "Pagos" }, { value: "cancelled", label: "Cancelados" }]} placeholder="Todos" aria-label="Situação" />
        {can("finance.manage") && <Button className="sm:ml-auto" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Novo lançamento</Button>}
      </Toolbar>
      <DataTable<Entry> rows={q.data?.results} loading={q.isLoading} error={q.error} columns={[
        { key: "due_date", header: "Vencimento", render: (e) => <span className="inline-flex items-center gap-1.5">{date(e.due_date)}{e.is_overdue && <Badge tone="critical">Vencida</Badge>}</span> },
        { key: "description", header: "Descrição", render: (e) => <div><div className="font-medium">{e.description}</div><div className="text-xs text-stone-500">{e.category_name}{e.supplier_name ? ` · ${e.supplier_name}` : ""}</div></div> },
        { key: "amount", header: "Valor", align: "right", render: (e) => brl(e.amount) },
        { key: "status", header: "Situação", render: (e) => <StatusBadge status={e.status} label={e.status === "paid" ? `Pago em ${date(e.paid_at)}` : e.status_label} /> },
        { key: "act", header: "", align: "right", render: (e) => can("finance.manage") && (
          <div className="flex justify-end gap-1">
            {e.status === "open" && <Button size="sm" variant="secondary" onClick={() => setPay(e)}>{e.kind === "payable" ? "Pagar" : "Receber"}</Button>}
            {e.status === "open" && <Button size="sm" variant="ghost" onClick={() => setCancel(e)}>Cancelar</Button>}
            {e.status === "paid" && <Button size="sm" variant="ghost" onClick={() => reopen.mutate(e.id)}>Estornar</Button>}
          </div>) },
      ]} />
      {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
      <Modal open={open} onOpenChange={setOpen} title="Novo lançamento">{open && <EntryForm onDone={() => setOpen(false)} />}</Modal>
      <ConfirmDialog open={!!pay} onOpenChange={(v) => !v && setPay(null)} title={pay ? `${pay.kind === "payable" ? "Pagar" : "Receber"}: ${pay.description}` : ""} loading={doPay.isPending}
        description={pay && `Valor: ${brl(pay.amount)}`} onConfirm={() => doPay.mutate(undefined)} confirmLabel="Confirmar">
        <Input label="Data" type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} />
      </ConfirmDialog>
      <ConfirmDialog open={!!cancel} onOpenChange={(v) => !v && setCancel(null)} title="Cancelar lançamento" danger requireReason loading={doCancel.isPending} onConfirm={(r) => doCancel.mutate(r)} />
    </>
  );
}

function CashTab() {
  const { can } = useAuth();
  const cur = useApi<Cash | null>("/cash-sessions/current/");
  const hist = useApi<Page<Cash>>("/cash-sessions/");
  const [opening, setOpening] = useState("");
  const [mv, setMv] = useState<"" | "supply" | "withdrawal">("");
  const [amount, setAmount] = useState("");
  const [closeOpen, setCloseOpen] = useState(false);
  const [counted, setCounted] = useState("");
  const open = useAction(() => api.post("/cash-sessions/open/", { opening_amount: opening.replace(",", ".") || "0" }), { success: "Caixa aberto." });
  const move = useAction((reason: string) => api.post(`/cash-sessions/${cur.data!.id}/movement/`, { kind: mv, amount: amount.replace(",", "."), reason }), { success: "Movimento registrado.", onSuccess: () => { setMv(""); setAmount(""); } });
  const close = useAction((notes: string) => api.post(`/cash-sessions/${cur.data!.id}/close/`, { counted_amount: counted.replace(",", "."), notes }), { success: "Caixa fechado.", onSuccess: () => setCloseOpen(false) });
  const c = cur.data;
  return (
    <div className="space-y-5 p-4">
      {cur.isLoading ? <Spinner /> : !c ? (
        <Card className="bg-stone-50">
          <EmptyState title="Caixa fechado" description="Abra o caixa informando o valor em dinheiro na gaveta." action={can("finance.manage") && (
            <div className="flex gap-2"><Input inputMode="decimal" placeholder="Valor de abertura" value={opening} onChange={(e) => setOpening(e.target.value)} aria-label="Valor de abertura" /><Button loading={open.isPending} onClick={() => open.mutate(undefined)}>Abrir caixa</Button></div>
          )} />
        </Card>
      ) : (
        <Card>
          <CardHeader title={`Caixa aberto desde ${dateTime(c.opened_at)}`} description={`por ${c.opened_by_name}`}
            actions={can("finance.manage") && <>
              <Button size="sm" variant="secondary" onClick={() => setMv("supply")}>Suprimento</Button>
              <Button size="sm" variant="secondary" onClick={() => setMv("withdrawal")}>Sangria</Button>
              <Button size="sm" onClick={() => setCloseOpen(true)}>Fechar caixa</Button>
            </>} />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <Stat label="Abertura" value={brl(c.breakdown.opening)} /><Stat label="Vendas em dinheiro" value={brl(c.breakdown.cash_sales)} />
            <Stat label="Suprimentos" value={brl(c.breakdown.supplies)} /><Stat label="Sangrias" value={brl(c.breakdown.withdrawals)} />
            <Stat label="Esperado na gaveta" value={brl(c.breakdown.expected)} />
          </div>
          {c.movements.length > 0 && <ul className="mt-4 divide-y divide-stone-100 text-sm">{c.movements.map((m) => <li key={m.id} className="flex justify-between py-1.5"><span>{m.kind_label} · {m.reason} <span className="text-xs text-stone-500">({m.user_name}, {dateTime(m.created_at)})</span></span><span className="num">{brl(m.amount)}</span></li>)}</ul>}
        </Card>
      )}
      <div>
        <h3 className="mb-2 text-sm font-semibold">Fechamentos anteriores</h3>
        <DataTable<Cash> rows={hist.data?.results.filter((h) => h.status === "closed")} loading={hist.isLoading} dense columns={[
          { key: "opened_at", header: "Abertura", render: (h) => dateTime(h.opened_at) }, { key: "closed_at", header: "Fechamento", render: (h) => `${dateTime(h.closed_at)} · ${h.closed_by_name}` },
          { key: "expected_amount", header: "Esperado", align: "right", render: (h) => brl(h.expected_amount) }, { key: "counted_amount", header: "Contado", align: "right", render: (h) => brl(h.counted_amount) },
          { key: "difference", header: "Diferença", align: "right", render: (h) => <span className={toNum(h.difference) < 0 ? "text-red-700" : toNum(h.difference) > 0 ? "text-amber-800" : ""}>{brl(h.difference)}</span> },
        ]} />
      </div>
      <ConfirmDialog open={!!mv} onOpenChange={(v) => !v && setMv("")} title={mv === "supply" ? "Suprimento (entrada de dinheiro)" : "Sangria (retirada de dinheiro)"} requireReason loading={move.isPending} onConfirm={(r) => move.mutate(r)}>
        <Input label="Valor (R$)" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </ConfirmDialog>
      <ConfirmDialog open={closeOpen} onOpenChange={setCloseOpen} title="Fechar caixa" reasonLabel="Observações" loading={close.isPending} confirmLabel="Fechar caixa"
        description={c && `Esperado na gaveta: ${brl(c.breakdown.expected)}. Conte o dinheiro e informe o valor encontrado.`} onConfirm={(n) => close.mutate(n)}>
        <Input label="Valor contado (R$)" inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} />
      </ConfirmDialog>
    </div>
  );
}

export default function Finance() {
  const { units } = useAuth();
  const [tab, setTab] = useState<"summary" | "entries" | "cash">("summary");
  const [start, setStart] = useState(monthStartISO());
  const [end, setEnd] = useState(todayISO());
  const [scope, setScope] = useState("unit");
  return (
    <div>
      <PageHeader title="Financeiro" description="Receitas, custos, despesas, contas e caixa. Indicadores com definições e limitações explícitas."
        actions={tab === "summary" && <>
          <Input type="date" className="w-40" value={start} onChange={(e) => setStart(e.target.value)} aria-label="De" />
          <Input type="date" className="w-40" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="Até" />
          {units.length > 1 && <Segmented value={scope} onChange={setScope} items={[{ value: "unit", label: "Unidade" }, { value: "all", label: "Consolidado" }]} />}
        </>} />
      <Tabs className="mb-5" value={tab} onChange={setTab} items={[{ value: "summary", label: "Resultado" }, { value: "entries", label: "Contas a pagar e receber" }, { value: "cash", label: "Caixa" }]} />
      {tab === "summary" && <SummaryTab start={start} end={end} scope={scope} />}
      {tab === "entries" && <Card padded={false}><EntriesTab /></Card>}
      {tab === "cash" && <Card padded={false}><CashTab /></Card>}
    </div>
  );
}
