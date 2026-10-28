import { useRef, useState } from "react";
import { AlertTriangle, FileUp, Plus, Upload } from "lucide-react";
import { api, newKey, type Page } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime, int, monthStartISO, todayISO } from "@/lib/format";
import {
  Badge, Button, Card, Checkbox, ConfirmDialog, DataTable, DefinitionList, Input, Modal, Notice, PageHeader, Pagination, Select,
  Stat, StatusBadge, Tabs, Toolbar, InfoTip,
} from "@/components/ui";
import { ORIGINS, PAYMENTS, type MenuItem } from "@/components/domain/types";

type Sale = {
  id: number; order_number: number | null; source: string; source_label: string; external_id: string | null; channel: string; channel_label: string;
  payment_label: string; occurred_at: string; gross_amount: string; discount_amount: string; fee_amount: string; delivery_fee: string; net_amount: string;
  cogs: string; status: string; status_label: string; stock_status: string; stock_status_label: string; cancel_reason: string; created_by_name: string | null;
  items: { id: number; description: string; quantity: string; unit_price: string; discount: string; total: string; stock_warning: string }[];
};
type Summary = { sales_count: number; gross: string; discounts: string; fees: string; delivery_fees: string; net: string; cogs: string;
  cancelled_value: string; cancelled_count: number; average_ticket: string; without_recipe: number };
type Batch = { id: number; filename: string; created_at: string; rows_total: number; sales_imported: number; sales_duplicated: number;
  rows_failed: number; errors: { linha?: number; venda?: string; erro: unknown }[]; unmapped_codes: string[]; user_name: string | null };

function SaleDetail({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [ret, setRet] = useState(false);
  const cancel = useAction((reason: string) => api.post(`/sales/${sale.id}/cancel/`, { reason, return_to_stock: ret }), { success: "Venda cancelada.", onSuccess: onClose });
  return (
    <div className="space-y-4">
      <DefinitionList items={[
        ["Data", dateTime(sale.occurred_at)], ["Origem", `${sale.source_label}${sale.order_number ? ` · pedido #${sale.order_number}` : ""}`],
        ["Canal", sale.channel_label], ["Pagamento", sale.payment_label || "—"], ["Identificador", sale.external_id || `#${sale.id}`],
        ["Estoque", sale.stock_status_label], ["Status", <StatusBadge status={sale.status} label={sale.status_label} />],
        ...(sale.cancel_reason ? [["Motivo", sale.cancel_reason] as [string, string]] : []),
      ]} />
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-stone-500"><th className="py-1.5">Item</th><th className="py-1.5 text-right">Qtd.</th><th className="py-1.5 text-right">Total</th></tr></thead>
        <tbody className="divide-y divide-stone-100">
          {sale.items.map((i) => (
            <tr key={i.id}><td className="py-1.5">{i.description}{i.stock_warning && <div className="flex items-center gap-1 text-xs text-amber-800"><AlertTriangle className="h-3 w-3" />{i.stock_warning}</div>}</td>
              <td className="num py-1.5 text-right">{Number(i.quantity)}</td><td className="num py-1.5 text-right">{brl(i.total)}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="grid grid-cols-2 gap-3 rounded-lg bg-stone-50 p-3 sm:grid-cols-3">
        <Stat label="Bruto" value={brl(sale.gross_amount)} /><Stat label="Descontos" value={brl(sale.discount_amount)} />
        <Stat label="Taxas" value={brl(sale.fee_amount)} /><Stat label="Taxa de entrega" value={brl(sale.delivery_fee)} />
        <Stat label="Líquido" value={brl(sale.net_amount)} /><Stat label="CMV real" value={brl(sale.cogs)} />
      </div>
      {sale.status === "completed" && can("sales.cancel") && <Button variant="secondary" className="text-red-800" onClick={() => setOpen(true)}>Cancelar venda</Button>}
      <ConfirmDialog open={open} onOpenChange={setOpen} title="Cancelar venda" danger requireReason confirmLabel="Cancelar venda" loading={cancel.isPending}
        description="O cancelamento é registrado na auditoria e não apaga a venda." onConfirm={(r) => cancel.mutate(r)}>
        <Checkbox checked={ret} onChange={(e) => setRet(e.target.checked)} label="Devolver os itens ao estoque (estorno)"
          hint="Use apenas se os produtos voltaram intactos (ex.: bebida lacrada). Caso contrário, serão registrados como perda." />
      </ConfirmDialog>
    </div>
  );
}

function NewSale({ onDone }: { onDone: () => void }) {
  const items = useApi<Page<MenuItem>>("/menu-items/", { page_size: 500 });
  const [lines, setLines] = useState<{ menu_item: string; quantity: string }[]>([{ menu_item: "", quantity: "1" }]);
  const [channel, setChannel] = useState("counter");
  const [payment, setPayment] = useState("pix");
  const [discount, setDiscount] = useState("0");
  const [fee, setFee] = useState("0");
  const [key] = useState(newKey);
  const opts = (items.data?.results || []).map((i) => ({ value: i.id, label: `${i.name} — ${brl(i.price)}` }));
  const save = useAction(() => api.post("/sales/", {
    channel, payment_method: payment, discount: discount.replace(",", ".") || "0", fee: fee.replace(",", ".") || "0",
    items: lines.filter((l) => l.menu_item).map((l) => ({ menu_item: Number(l.menu_item), quantity: l.quantity.replace(",", ".") })),
  }, { "Idempotency-Key": key }), { success: "Venda registrada e ingredientes baixados.", onSuccess: onDone });
  return (
    <div className="space-y-4">
      <Notice>Use para vendas sem pedido (ex.: balcão rápido). Vendas de pedidos são registradas automaticamente na entrega.</Notice>
      {lines.map((l, idx) => (
        <div key={idx} className="flex gap-2">
          <Select className="flex-1" value={l.menu_item} onChange={(e) => setLines(lines.map((x, i) => (i === idx ? { ...x, menu_item: e.target.value } : x)))} options={opts} placeholder="Selecione o item" aria-label="Item" />
          <Input className="w-20" inputMode="decimal" value={l.quantity} onChange={(e) => setLines(lines.map((x, i) => (i === idx ? { ...x, quantity: e.target.value } : x)))} aria-label="Quantidade" />
        </div>
      ))}
      <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setLines([...lines, { menu_item: "", quantity: "1" }])}>Adicionar item</Button>
      <div className="grid grid-cols-2 gap-3">
        <Select label="Canal" value={channel} onChange={(e) => setChannel(e.target.value)} options={ORIGINS} />
        <Select label="Pagamento" value={payment} onChange={(e) => setPayment(e.target.value)} options={PAYMENTS} />
        <Input label="Desconto (R$)" inputMode="decimal" value={discount} onChange={(e) => setDiscount(e.target.value)} />
        <Input label="Taxas pagas (R$)" hint="Ex.: comissão do aplicativo" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} />
      </div>
      <div className="flex justify-end"><Button loading={save.isPending} disabled={!lines.some((l) => l.menu_item)} onClick={() => save.mutate(undefined)}>Registrar venda</Button></div>
    </div>
  );
}

function ImportCsv() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<Batch | null>(null);
  const batches = useApi<Page<Batch>>("/import-batches/");
  const upload = useAction(async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    return api.post<Batch>("/sales/import/", fd);
  }, { success: (b) => `Importação concluída: ${b.sales_imported} nova(s), ${b.sales_duplicated} já existente(s).`, onSuccess: setResult });
  const example = "id_venda;data_hora;canal;forma_pagamento;codigo_produto;descricao;quantidade;preco_unitario;desconto_item;taxa;cancelada\n" +
    "V1001;2026-10-01 20:15;mesa;pix;PDV001;Batata frita;2;32,00;0;;nao\nV1002;01/10/2026 21:00;app;app;PDV007;Hambúrguer;1;36,00;0;4,32;nao\n";
  return (
    <div className="space-y-5 p-4">
      <Notice title="Importação por CSV (alternativa local à integração com PDV)">
        Cada venda deve ter um <strong>id_venda</strong> único: reimportar o mesmo arquivo não duplica vendas. Os códigos de produto são associados ao cardápio
        pelo “código no PDV” do item ou pela aba Mapeamento PDV. Separador “;” ou “,”.
      </Notice>
      <div className="flex flex-wrap gap-2">
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
        <Button icon={<Upload className="h-4 w-4" />} loading={upload.isPending} onClick={() => fileRef.current?.click()}>Selecionar arquivo CSV</Button>
        <Button variant="secondary" icon={<FileUp className="h-4 w-4" />} onClick={() => {
          const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + example], { type: "text/csv" })); a.download = "modelo_vendas.csv"; a.click();
        }}>Baixar modelo</Button>
      </div>
      {result && (
        <Card className="bg-stone-50">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Linhas lidas" value={int(result.rows_total)} /><Stat label="Vendas novas" value={int(result.sales_imported)} tone="good" />
            <Stat label="Já importadas" value={int(result.sales_duplicated)} /><Stat label="Erros" value={int(result.rows_failed)} tone={result.rows_failed ? "bad" : "default"} />
          </div>
          {result.unmapped_codes.length > 0 && <Notice tone="warning" title="Códigos sem mapeamento (baixa de estoque não realizada)">{result.unmapped_codes.join(", ")}</Notice>}
          {result.errors.length > 0 && <ul className="mt-3 space-y-1 text-xs text-red-800">{result.errors.slice(0, 20).map((e, i) => <li key={i}>{e.linha ? `Linha ${e.linha}` : `Venda ${e.venda}`}: {typeof e.erro === "string" ? e.erro : JSON.stringify(e.erro)}</li>)}</ul>}
        </Card>
      )}
      <div>
        <h3 className="mb-2 text-sm font-semibold">Importações anteriores</h3>
        <DataTable<Batch> rows={batches.data?.results} loading={batches.isLoading} dense columns={[
          { key: "created_at", header: "Data", render: (b) => dateTime(b.created_at) }, { key: "filename", header: "Arquivo" },
          { key: "sales_imported", header: "Novas", align: "right" }, { key: "sales_duplicated", header: "Duplicadas", align: "right" },
          { key: "rows_failed", header: "Erros", align: "right" }, { key: "user_name", header: "Usuário", hideOnMobile: true },
        ]} />
      </div>
    </div>
  );
}

function Mappings() {
  const { can } = useAuth();
  const list = useApi<Page<{ id: number; external_code: string; external_name: string; menu_item: number; menu_item_name: string }>>("/pos-mappings/", { page_size: 200 });
  const unmapped = useApi<string[]>("/pos-mappings/unmapped/");
  const menu = useOptions("/menu-items/");
  const [code, setCode] = useState("");
  const [item, setItem] = useState("");
  const add = useAction(() => api.post("/pos-mappings/", { source: "csv", external_code: code, menu_item: Number(item) }), { success: "Mapeamento salvo.", onSuccess: () => { setCode(""); setItem(""); } });
  const del = useAction((id: number) => api.del(`/pos-mappings/${id}/`), { success: "Mapeamento removido." });
  return (
    <div className="space-y-4 p-4">
      {unmapped.data && unmapped.data.length > 0 && <Notice tone="warning" title="Códigos importados sem mapeamento">{unmapped.data.map((c) => <button key={c} className="mr-2 underline" onClick={() => setCode(c)}>{c}</button>)}</Notice>}
      {can("sales.manage") && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input placeholder="Código no PDV" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Código no PDV" />
          <Select value={item} onChange={(e) => setItem(e.target.value)} options={menu.options} placeholder="Item do cardápio" aria-label="Item do cardápio" />
          <Button disabled={!code || !item} loading={add.isPending} onClick={() => add.mutate(undefined)}>Mapear</Button>
        </div>
      )}
      <DataTable rows={list.data?.results} loading={list.isLoading} dense columns={[
        { key: "external_code", header: "Código PDV" }, { key: "menu_item_name", header: "Item do cardápio" },
        { key: "a", header: "", align: "right", render: (r) => can("sales.manage") && <Button size="sm" variant="ghost" onClick={() => del.mutate(r.id)}>Remover</Button> },
      ]} />
    </div>
  );
}

export default function Sales() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"list" | "import" | "map">("list");
  const [start, setStart] = useState(monthStartISO());
  const [end, setEnd] = useState(todayISO());
  const [status, setStatus] = useState("");
  const [channel, setChannel] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Sale | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const params = { start, end, status: status || undefined, channel: channel || undefined, page, ordering: "-occurred_at" };
  const q = useApi<Page<Sale>>("/sales/", params);
  const sum = useApi<Summary>("/sales/summary/", { start, end });
  const s = sum.data;
  return (
    <div>
      <PageHeader title="Vendas" description="Faturamento bruto, descontos, taxas e receita líquida, com o custo real dos ingredientes de cada venda."
        actions={can("sales.manage") && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setNewOpen(true)}>Registrar venda</Button>} />
      {s && (
        <Card className="mb-5">
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Vendas" value={int(s.sales_count)} hint={s.cancelled_count ? `${s.cancelled_count} cancelada(s)` : undefined} />
            <Stat label="Faturamento bruto" value={brl(s.gross)} />
            <Stat label="Descontos + taxas" value={brl(Number(s.discounts) + Number(s.fees))} />
            <Stat label={<span className="inline-flex items-center gap-1">Receita líquida <InfoTip>Bruto − descontos − taxas de plataforma + taxas de entrega cobradas.</InfoTip></span>} value={brl(s.net)} />
            <Stat label="Ticket médio" value={brl(s.average_ticket)} />
            <Stat label="CMV real" value={brl(s.cogs)} hint={s.without_recipe ? `${s.without_recipe} venda(s) com baixa incompleta` : undefined} tone={s.without_recipe ? "warn" : "default"} />
          </div>
        </Card>
      )}
      <Card padded={false}>
        <div className="px-4 pt-2"><Tabs value={tab} onChange={setTab} items={[{ value: "list", label: "Vendas" }, ...(can("sales.manage") ? [{ value: "import" as const, label: "Importar CSV" }] : []), { value: "map", label: "Mapeamento PDV" }]} /></div>
        {tab === "list" && (<>
          <Toolbar>
            <Input type="date" className="sm:w-40" value={start} onChange={(e) => { setStart(e.target.value); setPage(1); }} aria-label="De" />
            <Input type="date" className="sm:w-40" value={end} onChange={(e) => { setEnd(e.target.value); setPage(1); }} aria-label="Até" />
            <Select className="sm:w-44" value={channel} onChange={(e) => setChannel(e.target.value)} options={ORIGINS} placeholder="Todos os canais" aria-label="Canal" />
            <Select className="sm:w-40" value={status} onChange={(e) => setStatus(e.target.value)} options={[{ value: "completed", label: "Concluídas" }, { value: "cancelled", label: "Canceladas" }]} placeholder="Todas" aria-label="Situação" />
          </Toolbar>
          <DataTable<Sale> rows={q.data?.results} loading={q.isLoading} error={q.error} onRowClick={setSel} columns={[
            { key: "occurred_at", header: "Data", render: (r) => dateTime(r.occurred_at) },
            { key: "id", header: "Venda", render: (r) => <span>{r.external_id || `#${r.id}`}{r.order_number && <span className="text-stone-500"> · pedido #{r.order_number}</span>}</span> },
            { key: "channel", header: "Canal", hideOnMobile: true, render: (r) => r.channel_label },
            { key: "stock", header: "Estoque", hideOnMobile: true, render: (r) => r.stock_status === "partial" ? <Badge tone="warning" icon={<AlertTriangle className="h-3 w-3" />}>Baixa incompleta</Badge> : <span className="text-xs text-stone-500">{r.stock_status_label}</span> },
            { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} label={r.status_label} /> },
            { key: "net_amount", header: "Líquido", align: "right", render: (r) => brl(r.net_amount) },
            { key: "cogs", header: "CMV", align: "right", hideOnMobile: true, render: (r) => brl(r.cogs) },
          ]} />
          {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
        </>)}
        {tab === "import" && <ImportCsv />}
        {tab === "map" && <Mappings />}
      </Card>
      <Modal open={!!sel} onOpenChange={(v) => !v && setSel(null)} title={sel ? `Venda ${sel.external_id || `#${sel.id}`}` : ""}>{sel && <SaleDetail sale={sel} onClose={() => setSel(null)} />}</Modal>
      <Modal open={newOpen} onOpenChange={setNewOpen} title="Registrar venda">{newOpen && <NewSale onDone={() => setNewOpen(false)} />}</Modal>
    </div>
  );
}
