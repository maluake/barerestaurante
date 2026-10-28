import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Archive, Plus, Trash2 } from "lucide-react";
import { api, ApiError, type Page } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { brl, dateTime, pct, qty, toNum } from "@/lib/format";
import { Button, Card, CardHeader, Checkbox, FormGrid, Input, Notice, PageHeader, Select, Spinner, Stat, Textarea } from "@/components/ui";
import { ChartCard, TimeLines } from "@/components/charts/Charts";
import type { MenuItem, Product, Uom } from "@/components/domain/types";

type Cost = { recipe_total_cost: string; cost_per_portion: string; price: string; contribution_margin: string; margin_percent: string | null; complete: boolean;
  lines: { product: string; quantity: string; unit: string; loss_percent?: string; gross_quantity?: string; stock_unit?: string; unit_cost: string; cost: string }[];
  snapshots: { cost_per_portion: string; price: string; reason: string; created_at: string }[]; policy: string };
type Rev = { id: number; summary: string; user_name: string | null; created_at: string };
type Ing = { product: string; quantity: string; unit: string; loss_percent: string };

export default function MenuItemPage() {
  const { id } = useParams();
  const isNew = id === "novo";
  const nav = useNavigate();
  const { can } = useAuth();
  const editable = can("recipes.manage");
  const item = useApi<MenuItem>(isNew ? null : `/menu-items/${id}/`);
  const cost = useApi<Cost>(!isNew && can("costs.view") ? `/menu-items/${id}/cost/` : null);
  const revs = useApi<Rev[]>(!isNew ? `/menu-items/${id}/history/` : null);
  const products = useApi<Page<Product>>("/products/", { page_size: 500 });
  const uoms = useApi<Uom[]>("/units-of-measure/");
  const cats = useOptions("/menu-categories/");
  const [f, setF] = useState({ name: "", category: "", description: "", price: "", stock_mode: "recipe", yield_portions: "1", requires_preparation: true,
    prep_time_minutes: "", pos_code: "", is_available: true, direct_product: "", direct_quantity: "1", direct_unit: "" });
  const [ings, setIngs] = useState<Ing[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    const m = item.data;
    if (!m) return;
    setF({ name: m.name, category: String(m.category ?? ""), description: m.description, price: String(Number(m.price)), stock_mode: m.stock_mode,
      yield_portions: String(Number(m.yield_portions)), requires_preparation: m.requires_preparation, prep_time_minutes: String(m.prep_time_minutes ?? ""),
      pos_code: m.pos_code, is_available: m.is_available, direct_product: String(m.direct_product ?? ""), direct_quantity: String(Number(m.direct_quantity ?? 1)),
      direct_unit: String(m.direct_unit ?? "") });
    setIngs(m.ingredients.map((i) => ({ product: String(i.product), quantity: String(Number(i.quantity)), unit: String(i.unit), loss_percent: String(Number(i.loss_percent)) })));
  }, [item.data]);

  const prodMap = useMemo(() => new Map((products.data?.results || []).map((p) => [String(p.id), p])), [products.data]);
  const uomMap = useMemo(() => new Map((uoms.data || []).map((u) => [String(u.id), u])), [uoms.data]);

  // Prévia do custo enquanto edita (mesma fórmula do backend; o valor oficial vem do servidor ao salvar).
  const preview = useMemo(() => {
    let total = 0;
    let complete = ings.length > 0;
    for (const i of ings) {
      const p = prodMap.get(i.product);
      const u = uomMap.get(i.unit);
      const pu = p ? uomMap.get(String(p.unit)) : undefined;
      if (!p || !u || !pu) { complete = false; continue; }
      let factor: number | null = null;
      if (u.id === pu.id) factor = 1;
      else if (u.dimension === pu.dimension && u.factor_to_base && pu.factor_to_base) factor = Number(u.factor_to_base) / Number(pu.factor_to_base);
      if (factor === null) { complete = false; continue; }
      const loss = toNum(i.loss_percent.replace(",", ".")) / 100;
      total += (toNum(i.quantity.replace(",", ".")) / (1 - loss)) * factor * toNum(p.cost_price);
    }
    const per = total / Math.max(toNum(f.yield_portions.replace(",", ".")) || 1, 0.0001);
    const price = toNum(f.price.replace(",", "."));
    return { total, per, margin: price - per, marginPct: price ? ((price - per) / price) * 100 : null, complete };
  }, [ings, prodMap, uomMap, f.yield_portions, f.price]);

  const dec = (v: string) => v.replace(",", ".");
  const save = useAction(() => {
    const body = {
      name: f.name, category: f.category || null, description: f.description, price: dec(f.price), stock_mode: f.stock_mode, yield_portions: dec(f.yield_portions) || "1",
      requires_preparation: f.requires_preparation, prep_time_minutes: f.prep_time_minutes || null, pos_code: f.pos_code, is_available: f.is_available,
      direct_product: f.stock_mode === "direct" ? Number(f.direct_product) || null : null, direct_quantity: f.stock_mode === "direct" ? dec(f.direct_quantity) : null,
      direct_unit: f.stock_mode === "direct" && f.direct_unit ? Number(f.direct_unit) : null,
      ingredients: f.stock_mode === "recipe" ? ings.filter((i) => i.product && i.quantity).map((i) => ({ product: Number(i.product), quantity: dec(i.quantity), unit: Number(i.unit), loss_percent: dec(i.loss_percent || "0") })) : [],
    };
    return isNew ? api.post<MenuItem>("/menu-items/", body) : api.patch<MenuItem>(`/menu-items/${id}/`, body);
  }, { success: "Item salvo e custo recalculado.", onSuccess: (m) => isNew && nav(`/cardapio/${m.id}`, { replace: true }) });
  const archive = useAction(() => api.post(`/menu-items/${id}/archive/`), { success: "Situação atualizada." });
  const submit = () => { setErrors({}); save.mutate(undefined, { onError: (e) => e instanceof ApiError && setErrors(e.fieldErrors) }); };

  if (!isNew && !item.data) return <Spinner />;
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const productOpts = (products.data?.results || []).map((p) => ({ value: p.id, label: `${p.name} (${p.unit_code})` }));
  const compatibleUnits = (pid: string) => {
    const p = prodMap.get(pid);
    const pu = p ? uomMap.get(String(p.unit)) : undefined;
    const packIds = new Set((p?.packagings || []).map((x) => String(x.unit)));
    return (uoms.data || []).filter((u) => !pu || u.id === pu.id || (u.dimension === pu.dimension && u.dimension !== "package") || packIds.has(String(u.id))).map((u) => ({ value: u.id, label: u.code }));
  };
  const snaps = [...(cost.data?.snapshots || [])].reverse();

  return (
    <div>
      <PageHeader back={{ to: "/cardapio", label: "Cardápio" }} title={isNew ? "Novo item do cardápio" : f.name}
        actions={!isNew && editable && <Button variant="ghost" icon={<Archive className="h-4 w-4" />} onClick={() => archive.mutate(undefined)}>{item.data?.status === "active" ? "Arquivar" : "Reativar"}</Button>} />
      {!isNew && item.data && !item.data.has_reliable_recipe && (
        <div className="mb-4"><Notice tone="warning" icon={<AlertTriangle className="h-4 w-4" />} title="Baixa automática não confiável">
          Este item não tem ficha técnica. As vendas são registradas, mas os ingredientes não são baixados e o CMV fica incompleto.</Notice></div>
      )}
      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <div className="space-y-5">
          <Card>
            <CardHeader title="Dados do item" />
            <fieldset disabled={!editable} className="space-y-4">
              <FormGrid>
                <Input label="Nome" value={f.name} onChange={set("name")} error={errors.name} required />
                <Select label="Categoria" value={f.category} onChange={set("category")} options={cats.options} placeholder="Sem categoria" />
                <Input label="Preço de venda (R$)" inputMode="decimal" value={f.price} onChange={set("price")} error={errors.price} required />
                <Input label="Código no PDV" hint="Usado na importação de vendas" value={f.pos_code} onChange={set("pos_code")} />
              </FormGrid>
              <Textarea label="Descrição" value={f.description} onChange={set("description")} rows={2} />
              <FormGrid cols={3}>
                <Select label="Baixa de estoque" value={f.stock_mode} onChange={set("stock_mode")} options={[{ value: "recipe", label: "Pela ficha técnica" }, { value: "direct", label: "Revenda de um produto" }, { value: "none", label: "Sem baixa automática" }]} />
                <Input label="Tempo de preparo (min)" inputMode="numeric" value={f.prep_time_minutes} onChange={set("prep_time_minutes")} />
                <div className="space-y-2 pt-6">
                  <Checkbox label="Vai para a cozinha" checked={f.requires_preparation} onChange={set("requires_preparation")} />
                  <Checkbox label="Disponível para venda" checked={f.is_available} onChange={set("is_available")} />
                </div>
              </FormGrid>
            </fieldset>
          </Card>
          {f.stock_mode === "direct" && (
            <Card>
              <CardHeader title="Produto revendido" description="Ex.: 1 cerveja long neck vendida baixa 1 unidade do produto." />
              <fieldset disabled={!editable}><FormGrid cols={3}>
                <Select label="Produto" value={f.direct_product} onChange={set("direct_product")} options={productOpts} placeholder="Selecione" error={errors.direct_product} />
                <Input label="Quantidade por venda" inputMode="decimal" value={f.direct_quantity} onChange={set("direct_quantity")} />
                <Select label="Unidade" value={f.direct_unit} onChange={set("direct_unit")} options={compatibleUnits(f.direct_product)} placeholder="Unidade do produto" error={errors.direct_unit} />
              </FormGrid></fieldset>
            </Card>
          )}
          {f.stock_mode === "recipe" && (
            <Card padded={false}>
              <div className="flex flex-wrap items-end justify-between gap-3 p-5 pb-3">
                <div><h2 className="text-base font-semibold">Ficha técnica</h2><p className="text-sm text-stone-500">Quantidade líquida usada na receita. A perda de preparo aumenta a quantidade bruta baixada do estoque.</p></div>
                <Input label="Rendimento (porções)" className="w-32" inputMode="decimal" value={f.yield_portions} onChange={set("yield_portions")} disabled={!editable} />
              </div>
              {errors.ingredients && <div className="px-5 pb-2"><Notice tone="critical">{errors.ingredients}</Notice></div>}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-y border-stone-200 bg-stone-50 text-left text-xs text-stone-500">
                    <th className="px-4 py-2 font-semibold">Ingrediente</th><th className="px-2 py-2 font-semibold">Qtd. líquida</th><th className="px-2 py-2 font-semibold">Unid.</th>
                    <th className="px-2 py-2 font-semibold">Perda %</th><th className="px-4 py-2 text-right font-semibold">Custo</th><th />
                  </tr></thead>
                  <tbody className="divide-y divide-stone-100">
                    {ings.map((i, idx) => {
                      const p = prodMap.get(i.product);
                      const line = cost.data?.lines.find((l) => l.product === p?.name);
                      const upd = (k: keyof Ing, v: string) => setIngs(ings.map((x, j) => (j === idx ? { ...x, [k]: v, ...(k === "product" ? { unit: String(prodMap.get(v)?.unit ?? "") } : {}) } : x)));
                      return (
                        <tr key={idx}>
                          <td className="px-4 py-2"><Select value={i.product} onChange={(e) => upd("product", e.target.value)} options={productOpts} placeholder="Selecione" disabled={!editable} aria-label="Ingrediente" /></td>
                          <td className="px-2 py-2"><input className="input w-24" inputMode="decimal" value={i.quantity} onChange={(e) => upd("quantity", e.target.value)} disabled={!editable} aria-label="Quantidade" /></td>
                          <td className="px-2 py-2"><Select className="w-24" value={i.unit} onChange={(e) => upd("unit", e.target.value)} options={compatibleUnits(i.product)} disabled={!editable} aria-label="Unidade" /></td>
                          <td className="px-2 py-2"><input className="input w-20" inputMode="decimal" value={i.loss_percent} onChange={(e) => upd("loss_percent", e.target.value)} disabled={!editable} aria-label="Perda" /></td>
                          <td className="num px-4 py-2 text-right text-stone-700">{line ? brl(line.cost) : p ? <span className="text-stone-400">salve para calcular</span> : "—"}
                            {line?.gross_quantity && <div className="text-[11px] text-stone-400">bruto {qty(line.gross_quantity, line.stock_unit)}</div>}</td>
                          <td className="pr-3">{editable && <button className="p-2 text-stone-400 hover:text-red-700" onClick={() => setIngs(ings.filter((_, j) => j !== idx))} aria-label="Remover ingrediente"><Trash2 className="h-4 w-4" /></button>}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {editable && <div className="p-4"><Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setIngs([...ings, { product: "", quantity: "", unit: "", loss_percent: "0" }])}>Adicionar ingrediente</Button></div>}
            </Card>
          )}
          {editable && <div className="flex justify-end"><Button size="lg" loading={save.isPending} onClick={submit}>{isNew ? "Cadastrar item" : "Salvar alterações"}</Button></div>}
        </div>
        <div className="space-y-5">
          {can("costs.view") && (
            <Card>
              <CardHeader title="Custo e margem" description={cost.data ? "Valores oficiais calculados no servidor" : "Prévia enquanto você edita"} />
              <div className="grid grid-cols-2 gap-4">
                <Stat label="Custo da receita" value={brl(cost.data?.recipe_total_cost ?? preview.total)} />
                <Stat label="Custo por porção" value={brl(cost.data?.cost_per_portion ?? preview.per)} />
                <Stat label="Preço de venda" value={brl(f.price.replace(",", "."))} />
                <Stat label="Margem de contribuição" value={brl(cost.data?.contribution_margin ?? preview.margin)}
                  hint={pct(cost.data?.margin_percent ?? preview.marginPct)} tone={(toNum(cost.data?.contribution_margin ?? preview.margin)) < 0 ? "bad" : "good"} />
              </div>
              {cost.data && !cost.data.complete && <p className="mt-3 text-xs text-amber-800">Algum ingrediente está sem custo de compra: o custo pode estar subestimado.</p>}
              {cost.data && <p className="mt-3 text-xs text-stone-500">{cost.data.policy}</p>}
            </Card>
          )}
          {can("costs.view") && snaps.length > 1 && (
            <ChartCard title="Custo por porção ao longo do tempo" table={{ columns: ["Data", "Custo", "Preço", "Motivo"], rows: snaps.map((s) => [dateTime(s.created_at), brl(s.cost_per_portion), brl(s.price), s.reason]) }}>
              <TimeLines data={snaps.map((s) => ({ date: s.created_at.slice(0, 10), Custo: toNum(s.cost_per_portion) }))} xKey="date" xFmt={(v) => v.slice(8, 10) + "/" + v.slice(5, 7)} fmt={brl} series={[{ key: "Custo", name: "Custo/porção" }]} height={180} />
            </ChartCard>
          )}
          {!isNew && (
            <Card>
              <CardHeader title="Histórico de alterações" />
              <ol className="space-y-2.5 text-sm">
                {(revs.data || []).map((r) => <li key={r.id}><div className="text-stone-800">{r.summary}</div><div className="text-xs text-stone-500">{dateTime(r.created_at)} · {r.user_name || "Sistema"}</div></li>)}
              </ol>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
