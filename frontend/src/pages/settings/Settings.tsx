import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Download, Plus } from "lucide-react";
import { api, ApiError, type Page } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import {
  Badge, Button, Card, CardHeader, Checkbox, DataTable, FormGrid, Input, Modal, Notice, PageHeader, Pagination, Select, Spinner, Tabs, useToast,
} from "@/components/ui";
import type { Uom } from "@/components/domain/types";

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function ProfileTab() {
  const { me, membership } = useAuth();
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const change = useAction(() => api.post("/auth/change-password/", { current_password: cur, new_password: nw }), { success: "Senha alterada.", onSuccess: () => { setCur(""); setNw(""); } });
  const exportData = async () => {
    try {
      const data = await api.get("/auth/my-data/");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      a.download = "meus-dados.json";
      a.click();
    } catch (e) { toast.error(e); }
  };
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader title="Meu perfil" />
        <dl className="space-y-2 text-sm"><div><dt className="text-xs text-stone-500">Nome</dt><dd>{me?.user.full_name}</dd></div>
          <div><dt className="text-xs text-stone-500">Usuário</dt><dd>{me?.user.username}</dd></div><div><dt className="text-xs text-stone-500">E-mail</dt><dd>{me?.user.email || "—"}</dd></div>
          <div><dt className="text-xs text-stone-500">Função</dt><dd>{membership?.role_label} · {membership?.organization.name}</dd></div></dl>
        <div className="mt-5 border-t border-stone-100 pt-4">
          <h3 className="text-sm font-semibold">Privacidade (LGPD)</h3>
          <p className="mt-1 text-sm text-stone-600">Exporte os dados pessoais associados à sua conta. Para exclusão, fale com o proprietário do estabelecimento.</p>
          <Button className="mt-3" variant="secondary" icon={<Download className="h-4 w-4" />} onClick={exportData}>Exportar meus dados</Button>
        </div>
      </Card>
      <Card>
        <CardHeader title="Alterar senha" />
        <div className="space-y-3">
          <Input label="Senha atual" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} error={errors.current_password} />
          <Input label="Nova senha" type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} error={errors.new_password} hint="Mínimo de 8 caracteres, não apenas números" />
          <Button loading={change.isPending} disabled={!cur || !nw} onClick={() => { setErrors({}); change.mutate(undefined, { onError: (e) => e instanceof ApiError && setErrors(e.fieldErrors) }); }}>Alterar senha</Button>
        </div>
      </Card>
    </div>
  );
}

type Org = { id: number; name: string; legal_name: string; cnpj: string; plan: string; is_demo: boolean; effective_settings: Record<string, unknown> };

function EstablishmentTab() {
  const q = useApi<Org>("/organization/");
  const [f, setF] = useState<Record<string, string>>({});
  const [weekdays, setWeekdays] = useState<number[]>([]);
  useEffect(() => {
    if (!q.data) return;
    const s = q.data.effective_settings;
    setF({ name: q.data.name, legal_name: q.data.legal_name, cnpj: q.data.cnpj, purchase_approval_threshold: String(s.purchase_approval_threshold), stale_quote_days: String(s.stale_quote_days),
      expiry_buckets: (s.expiry_buckets as number[]).join(", "), coverage_days: String(s.coverage_days), slow_order_minutes: String(s.slow_order_minutes),
      delivery_app_fee_percent: String(s.delivery_app_fee_percent), waste_alert_percent: String(s.waste_alert_percent), cost_increase_alert_percent: String(s.cost_increase_alert_percent) });
    setWeekdays(s.operating_weekdays as number[]);
  }, [q.data]);
  const save = useAction(() => api.patch("/organization/", {
    name: f.name, legal_name: f.legal_name, cnpj: f.cnpj,
    settings: { purchase_approval_threshold: f.purchase_approval_threshold.replace(",", "."), stale_quote_days: Number(f.stale_quote_days), coverage_days: Number(f.coverage_days),
      expiry_buckets: f.expiry_buckets.split(/[,;\s]+/).map(Number).filter((n) => n > 0).sort((a, b) => a - b), operating_weekdays: weekdays, slow_order_minutes: Number(f.slow_order_minutes),
      delivery_app_fee_percent: f.delivery_app_fee_percent.replace(",", "."), waste_alert_percent: f.waste_alert_percent.replace(",", "."), cost_increase_alert_percent: f.cost_increase_alert_percent.replace(",", ".") },
  }), { success: "Configurações salvas." });
  if (!q.data) return <Spinner />;
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Card>
      <CardHeader title="Estabelecimento e regras de negócio" description={`Plano: ${q.data.plan}${q.data.is_demo ? " · ambiente de demonstração" : ""}`} />
      <div className="space-y-5">
        <FormGrid cols={3}><Input label="Nome" value={f.name || ""} onChange={set("name")} /><Input label="Razão social" value={f.legal_name || ""} onChange={set("legal_name")} /><Input label="CNPJ" value={f.cnpj || ""} onChange={set("cnpj")} /></FormGrid>
        <FormGrid cols={3}>
          <Input label="Aprovação de compras acima de (R$)" inputMode="decimal" value={f.purchase_approval_threshold || ""} onChange={set("purchase_approval_threshold")} />
          <Input label="Cotação desatualizada após (dias)" inputMode="numeric" value={f.stale_quote_days || ""} onChange={set("stale_quote_days")} />
          <Input label="Faixas de vencimento (dias)" hint="Ex.: 3, 7, 30" value={f.expiry_buckets || ""} onChange={set("expiry_buckets")} />
          <Input label="Cobertura da lista de compras (dias)" inputMode="numeric" value={f.coverage_days || ""} onChange={set("coverage_days")} />
          <Input label="Pedido atrasado após (minutos)" inputMode="numeric" value={f.slow_order_minutes || ""} onChange={set("slow_order_minutes")} />
          <Input label="Taxa média dos aplicativos (%)" inputMode="decimal" value={f.delivery_app_fee_percent || ""} onChange={set("delivery_app_fee_percent")} />
          <Input label="Alerta de desperdício acima de (% das compras)" inputMode="decimal" value={f.waste_alert_percent || ""} onChange={set("waste_alert_percent")} />
          <Input label="Alerta de aumento de custo acima de (%)" inputMode="decimal" value={f.cost_increase_alert_percent || ""} onChange={set("cost_increase_alert_percent")} />
        </FormGrid>
        <div>
          <p className="mb-2 text-sm font-medium text-stone-700">Dias de funcionamento <span className="font-normal text-stone-500">(usados na previsão de consumo)</span></p>
          <div className="flex flex-wrap gap-2">{WEEKDAYS.map((d, i) => (
            <button key={d} onClick={() => setWeekdays((w) => (w.includes(i) ? w.filter((x) => x !== i) : [...w, i].sort()))}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${weekdays.includes(i) ? "bg-pine-800 text-white" : "bg-stone-100 text-stone-600"}`}>{d}</button>
          ))}</div>
        </div>
        <div className="flex justify-end"><Button loading={save.isPending} onClick={() => save.mutate(undefined)}>Salvar</Button></div>
      </div>
    </Card>
  );
}

function UnitsTab() {
  const q = useApi<{ id: number; name: string; code: string; city: string; address: string; is_active: boolean }[] | Page<{ id: number; name: string; code: string; city: string; address: string; is_active: boolean }>>("/units/");
  const { refresh } = useAuth();
  const [f, setF] = useState({ name: "", code: "", city: "", address: "" });
  const add = useAction(() => api.post("/units/", f), { success: "Unidade criada.", onSuccess: () => { setF({ name: "", code: "", city: "", address: "" }); refresh(); } });
  const rows = Array.isArray(q.data) ? q.data : q.data?.results;
  return (
    <Card padded={false}>
      <div className="p-5"><CardHeader title="Unidades" description="Cada unidade tem estoque, equipe, pedidos e movimentações próprios. Fornecedores, produtos e cardápio são compartilhados." />
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input placeholder="Nome da unidade" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-label="Nome" />
          <Input placeholder="Código" className="sm:w-28" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} aria-label="Código" />
          <Input placeholder="Cidade" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} aria-label="Cidade" />
          <Button icon={<Plus className="h-4 w-4" />} disabled={!f.name} loading={add.isPending} onClick={() => add.mutate(undefined)}>Adicionar</Button>
        </div>
      </div>
      <DataTable rows={rows} loading={q.isLoading} columns={[{ key: "name", header: "Nome" }, { key: "code", header: "Código" }, { key: "city", header: "Cidade" },
        { key: "is_active", header: "Situação", render: (u) => u.is_active ? <Badge tone="good">Ativa</Badge> : <Badge>Inativa</Badge> }]} />
    </Card>
  );
}

type Member = { id: number; user: { username: string; full_name: string; email: string }; role: string; role_label: string; units: number[]; extra_permissions: string[];
  revoked_permissions: string[]; is_active: boolean; permissions: string[] };
type Catalog = { permissions: { code: string; label: string }[]; roles: { code: string; label: string; permissions: string[] }[] };

function MemberForm({ member, catalog, onDone }: { member?: Member; catalog: Catalog; onDone: () => void }) {
  const { units } = useAuth();
  const [f, setF] = useState({ username: "", first_name: "", last_name: "", email: "", password: "", role: member?.role || "attendant", is_active: member?.is_active ?? true });
  const [unitIds, setUnitIds] = useState<number[]>(member?.units || []);
  const [extra, setExtra] = useState<string[]>(member?.extra_permissions || []);
  const [revoked, setRevoked] = useState<string[]>(member?.revoked_permissions || []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const base = new Set(catalog.roles.find((r) => r.code === f.role)?.permissions || []);
  const effective = (code: string) => (base.has(code) && !revoked.includes(code)) || extra.includes(code);
  const toggle = (code: string) => {
    if (base.has(code)) setRevoked((r) => (r.includes(code) ? r.filter((x) => x !== code) : [...r, code]));
    else setExtra((e) => (e.includes(code) ? e.filter((x) => x !== code) : [...e, code]));
  };
  const save = useAction(() => {
    const body = { role: f.role, is_active: f.is_active, units: unitIds, extra_permissions: extra.filter((p) => !base.has(p)), revoked_permissions: revoked.filter((p) => base.has(p)) };
    return member ? api.patch(`/team/${member.id}/`, body) : api.post("/team/", { ...body, username: f.username, first_name: f.first_name, last_name: f.last_name, email: f.email, password: f.password });
  }, { success: "Funcionário salvo.", onSuccess: onDone });
  return (
    <div className="space-y-5">
      {!member && <FormGrid>
        <Input label="Nome" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
        <Input label="Sobrenome" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
        <Input label="Usuário" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} error={errors.username} required />
        <Input label="E-mail" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <Input label="Senha inicial" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} error={errors.password || errors.non_field_errors} required />
      </FormGrid>}
      <FormGrid>
        <Select label="Função" value={f.role} onChange={(e) => { setF({ ...f, role: e.target.value }); setExtra([]); setRevoked([]); }} options={catalog.roles.map((r) => ({ value: r.code, label: r.label }))} />
        <div className="pt-7"><Checkbox label="Acesso ativo" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /></div>
      </FormGrid>
      {units.length > 1 && (
        <div><p className="mb-2 text-sm font-medium text-stone-700">Unidades <span className="font-normal text-stone-500">(nenhuma marcada = todas)</span></p>
          <div className="flex flex-wrap gap-3">{units.map((u) => <Checkbox key={u.id} label={u.name} checked={unitIds.includes(u.id)} onChange={() => setUnitIds((x) => (x.includes(u.id) ? x.filter((y) => y !== u.id) : [...x, u.id]))} />)}</div></div>
      )}
      {f.role !== "owner" && (
        <div>
          <p className="mb-2 text-sm font-medium text-stone-700">Permissões <span className="font-normal text-stone-500">(padrão da função, com ajustes individuais)</span></p>
          <div className="grid max-h-72 gap-1.5 overflow-y-auto rounded-lg p-3 ring-1 ring-stone-200 sm:grid-cols-2">
            {catalog.permissions.map((p) => (
              <Checkbox key={p.code} checked={effective(p.code)} onChange={() => toggle(p.code)}
                label={<span>{p.label}{base.has(p.code) ? "" : extra.includes(p.code) ? <Badge tone="pine" className="ml-1">extra</Badge> : ""}{base.has(p.code) && revoked.includes(p.code) ? <Badge tone="critical" className="ml-1">revogada</Badge> : ""}</span>} />
            ))}
          </div>
          <p className="mt-2 text-xs text-stone-500">As permissões são verificadas no servidor em todas as operações.</p>
        </div>
      )}
      <div className="flex justify-end"><Button loading={save.isPending} onClick={() => { setErrors({}); save.mutate(undefined, { onError: (e) => e instanceof ApiError && setErrors(e.fieldErrors) }); }}>Salvar</Button></div>
    </div>
  );
}

function TeamTab() {
  const q = useApi<Page<Member>>("/team/", { page_size: 200 });
  const catalog = useApi<Catalog>("/team/catalog/");
  const [edit, setEdit] = useState<Member | "new" | null>(null);
  return (
    <Card padded={false}>
      <div className="flex flex-wrap items-center justify-between gap-3 p-5"><div><h2 className="font-semibold">Equipe e permissões</h2><p className="text-sm text-stone-500">Proprietário, gerente, estoquista, atendente e cozinha.</p></div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setEdit("new")}>Novo funcionário</Button></div>
      <DataTable<Member> rows={q.data?.results} loading={q.isLoading} onRowClick={(m) => setEdit(m)} columns={[
        { key: "name", header: "Nome", render: (m) => <div><div className="font-medium">{m.user.full_name}</div><div className="text-xs text-stone-500">{m.user.username}</div></div> },
        { key: "role_label", header: "Função" },
        { key: "perms", header: "Ajustes", hideOnMobile: true, render: (m) => <span className="text-xs text-stone-500">{m.extra_permissions.length ? `+${m.extra_permissions.length} ` : ""}{m.revoked_permissions.length ? `−${m.revoked_permissions.length}` : ""}{!m.extra_permissions.length && !m.revoked_permissions.length ? "Padrão da função" : ""}</span> },
        { key: "is_active", header: "Acesso", render: (m) => m.is_active ? <Badge tone="good">Ativo</Badge> : <Badge>Inativo</Badge> },
      ]} />
      <Modal open={!!edit} onOpenChange={(v) => !v && setEdit(null)} title={edit === "new" ? "Novo funcionário" : edit ? edit.user.full_name : ""} size="lg">
        {edit && catalog.data && <MemberForm member={edit === "new" ? undefined : edit} catalog={catalog.data} onDone={() => setEdit(null)} />}
      </Modal>
    </Card>
  );
}

function SimpleList({ title, url, fields, description }: { title: string; url: string; description?: string; fields: { key: string; label: string; options?: { value: string; label: string }[] }[] }) {
  const q = useApi<{ id: number; [k: string]: unknown }[]>(url);
  const [f, setF] = useState<Record<string, string>>({});
  const add = useAction(() => api.post(url, f), { success: "Cadastro salvo.", onSuccess: () => setF({}) });
  const del = useAction((id: number) => api.del(`${url}${id}/`), { success: "Removido." });
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <div className="mb-3 flex flex-col gap-2 sm:flex-row">
        {fields.map((fl) => fl.options ? <Select key={fl.key} value={f[fl.key] || ""} onChange={(e) => setF({ ...f, [fl.key]: e.target.value })} options={fl.options} placeholder={fl.label} aria-label={fl.label} />
          : <Input key={fl.key} placeholder={fl.label} value={f[fl.key] || ""} onChange={(e) => setF({ ...f, [fl.key]: e.target.value })} aria-label={fl.label} />)}
        <Button disabled={!f[fields[0].key]} loading={add.isPending} onClick={() => add.mutate(undefined)}>Adicionar</Button>
      </div>
      <ul className="max-h-64 divide-y divide-stone-100 overflow-y-auto text-sm">
        {(q.data || []).map((r) => (
          <li key={r.id} className="flex items-center justify-between py-1.5">
            <span>{String(r.name)}{fields.slice(1).map((fl) => <span key={fl.key} className="ml-2 text-xs text-stone-500">{fl.options?.find((o) => o.value === r[fl.key])?.label ?? String(r[fl.key] ?? "")}</span>)}</span>
            <button className="text-xs text-stone-400 hover:text-red-700" onClick={() => del.mutate(r.id)}>remover</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CatalogsTab() {
  const uoms = useApi<Uom[]>("/units-of-measure/");
  const [u, setU] = useState({ code: "", name: "", dimension: "mass", factor_to_base: "" });
  const addU = useAction(() => api.post("/units-of-measure/", { ...u, factor_to_base: u.dimension === "package" ? null : u.factor_to_base.replace(",", ".") }), { success: "Unidade criada.", onSuccess: () => setU({ code: "", name: "", dimension: "mass", factor_to_base: "" }) });
  const dims = [{ value: "mass", label: "Massa (base g)" }, { value: "volume", label: "Volume (base ml)" }, { value: "count", label: "Contagem (base un)" }, { value: "package", label: "Embalagem" }];
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <SimpleList title="Categorias de produtos" url="/categories/" fields={[{ key: "name", label: "Nome" }, { key: "kind", label: "Tipo", options: [{ value: "ingredient", label: "Ingrediente" }, { value: "beverage", label: "Bebida" }, { value: "supply", label: "Descartável/limpeza" }, { value: "other", label: "Outro" }] }]} />
      <SimpleList title="Locais de armazenamento" url="/locations/" description="Por unidade" fields={[{ key: "name", label: "Nome" }, { key: "kind", label: "Tipo", options: [{ value: "dry", label: "Seco" }, { value: "chilled", label: "Refrigerado" }, { value: "frozen", label: "Congelado" }, { value: "bar", label: "Bar" }, { value: "other", label: "Outro" }] }]} />
      <SimpleList title="Categorias do cardápio" url="/menu-categories/" fields={[{ key: "name", label: "Nome" }]} />
      <SimpleList title="Categorias financeiras" url="/expense-categories/" fields={[{ key: "name", label: "Nome" }, { key: "kind", label: "Tipo", options: [{ value: "fixed", label: "Fixa" }, { value: "variable", label: "Variável" }, { value: "merchandise", label: "Mercadorias" }, { value: "payroll", label: "Folha" }, { value: "tax", label: "Impostos" }, { value: "fee", label: "Taxas" }, { value: "revenue", label: "Receita" }, { value: "other", label: "Outros" }] }]} />
      <Card className="lg:col-span-2">
        <CardHeader title="Unidades de medida" description="Conversões só entre unidades da mesma dimensão. Embalagens (caixa, fardo...) dependem do cadastro de embalagem de cada produto." />
        <div className="mb-3 flex flex-col gap-2 sm:flex-row">
          <Input placeholder="Código (ex.: lata)" value={u.code} onChange={(e) => setU({ ...u, code: e.target.value })} aria-label="Código" />
          <Input placeholder="Nome" value={u.name} onChange={(e) => setU({ ...u, name: e.target.value })} aria-label="Nome" />
          <Select value={u.dimension} onChange={(e) => setU({ ...u, dimension: e.target.value })} options={dims} aria-label="Dimensão" />
          {u.dimension !== "package" && <Input placeholder="Fator p/ base" value={u.factor_to_base} onChange={(e) => setU({ ...u, factor_to_base: e.target.value })} aria-label="Fator" />}
          <Button disabled={!u.code || !u.name} loading={addU.isPending} onClick={() => addU.mutate(undefined)}>Adicionar</Button>
        </div>
        <div className="flex flex-wrap gap-2">{(uoms.data || []).map((x) => <Badge key={x.id} tone={x.is_global ? "neutral" : "pine"}>{x.code} · {x.name}{x.factor_to_base ? ` = ${Number(x.factor_to_base)} ${x.dimension === "mass" ? "g" : x.dimension === "volume" ? "ml" : "un"}` : ""}</Badge>)}</div>
      </Card>
    </div>
  );
}

type Pref = { alert_type: string; label: string; enabled: boolean; min_priority: string; channels: string[] };
function AlertPrefsTab() {
  const q = useApi<Pref[]>("/alert-preferences/");
  const [rows, setRows] = useState<Pref[]>([]);
  useEffect(() => { if (q.data) setRows(q.data); }, [q.data]);
  const save = useAction(() => api.put("/alert-preferences/", rows), { success: "Preferências salvas." });
  const upd = (i: number, patch: Partial<Pref>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <Card padded={false}>
      <div className="p-5"><CardHeader title="Preferências de notificação" description="Escolha quais alertas notificar, a prioridade mínima e os canais. E-mail exige servidor SMTP configurado no backend." /></div>
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="border-y border-stone-200 bg-stone-50 text-left text-xs text-stone-500"><th className="px-4 py-2">Alerta</th><th className="px-4 py-2">Ativo</th><th className="px-4 py-2">Prioridade mínima</th><th className="px-4 py-2">No sistema</th><th className="px-4 py-2">E-mail</th></tr></thead>
        <tbody className="divide-y divide-stone-100">{rows.map((r, i) => (
          <tr key={r.alert_type}><td className="px-4 py-2">{r.label}</td>
            <td className="px-4 py-2"><input type="checkbox" checked={r.enabled} onChange={(e) => upd(i, { enabled: e.target.checked })} aria-label={`Ativar ${r.label}`} /></td>
            <td className="px-4 py-2"><Select className="w-32" value={r.min_priority} onChange={(e) => upd(i, { min_priority: e.target.value })} options={[{ value: "low", label: "Baixa" }, { value: "medium", label: "Média" }, { value: "high", label: "Alta" }, { value: "critical", label: "Crítica" }]} aria-label="Prioridade mínima" /></td>
            {["in_app", "email"].map((ch) => <td key={ch} className="px-4 py-2"><input type="checkbox" checked={r.channels.includes(ch)} aria-label={ch}
              onChange={(e) => upd(i, { channels: e.target.checked ? [...r.channels, ch] : r.channels.filter((c) => c !== ch) })} /></td>)}
          </tr>))}</tbody>
      </table></div>
      <div className="flex justify-end p-4"><Button loading={save.isPending} onClick={() => save.mutate(undefined)}>Salvar preferências</Button></div>
    </Card>
  );
}

function AuditTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useApi<Page<{ id: number; action: string; entity: string; summary: string; user_name: string; unit_name: string | null; ip_address: string | null; created_at: string }>>("/audit/", { page, search: search || undefined });
  return (
    <Card padded={false}>
      <div className="p-4"><Input placeholder="Buscar na auditoria" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} className="sm:w-80" aria-label="Buscar" /></div>
      <DataTable rows={q.data?.results} loading={q.isLoading} dense columns={[
        { key: "created_at", header: "Data", render: (r) => dateTime(r.created_at) }, { key: "user_name", header: "Usuário" },
        { key: "action", header: "Ação" }, { key: "entity", header: "Registro", hideOnMobile: true }, { key: "summary", header: "Resumo" },
        { key: "unit_name", header: "Unidade", hideOnMobile: true, render: (r) => r.unit_name || "—" }, { key: "ip_address", header: "IP", hideOnMobile: true, render: (r) => r.ip_address || "—" },
      ]} />
      {q.data && <Pagination page={page} count={q.data.count} onChange={setPage} />}
    </Card>
  );
}

function IntegrationsTab() {
  const cat = useApi<{ kind: string; provider: string; name: string; available: boolean; description: string; requires: string[] }[]>("/integration-catalog/");
  const logs = useApi<Page<{ id: number; kind: string; status: string; message: string; created_at: string }>>("/integration-logs/");
  return (
    <div className="space-y-5">
      <Notice>Integrações externas são opcionais. Credenciais ficam apenas em variáveis de ambiente do servidor, nunca no navegador.</Notice>
      <div className="grid gap-4 md:grid-cols-2">
        {cat.data?.map((c) => (
          <Card key={c.provider}>
            <div className="flex items-start justify-between gap-2"><h3 className="font-semibold">{c.name}</h3>{c.available ? <Badge tone="good">Disponível</Badge> : <Badge>Requer configuração externa</Badge>}</div>
            <p className="mt-1 text-sm text-stone-600">{c.description}</p>
            {c.requires.length > 0 && <p className="mt-2 text-xs text-stone-500">Necessário: {c.requires.join(" · ")}</p>}
          </Card>
        ))}
      </div>
      <Card padded={false}>
        <div className="p-5 pb-2"><h2 className="font-semibold">Registro de falhas e importações</h2></div>
        <DataTable rows={logs.data?.results} loading={logs.isLoading} dense columns={[
          { key: "created_at", header: "Data", render: (r) => dateTime(r.created_at) }, { key: "kind", header: "Tipo" },
          { key: "status", header: "Status", render: (r) => r.status === "failure" ? <Badge tone="critical">Falha</Badge> : <Badge tone="good">Sucesso</Badge> }, { key: "message", header: "Mensagem" },
        ]} />
      </Card>
    </div>
  );
}

const TABS = [
  { value: "perfil", label: "Meu perfil", perm: "" },
  { value: "estabelecimento", label: "Estabelecimento", perm: "settings.manage" },
  { value: "unidades", label: "Unidades", perm: "units.manage" },
  { value: "equipe", label: "Equipe e permissões", perm: "team.manage" },
  { value: "cadastros", label: "Cadastros auxiliares", perm: "products.manage" },
  { value: "alertas", label: "Notificações", perm: "alerts.view" },
  { value: "auditoria", label: "Auditoria", perm: "audit.view" },
  { value: "integracoes", label: "Integrações", perm: "integrations.manage" },
];

export default function Settings() {
  const { tab = "perfil" } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const tabs = TABS.filter((t) => !t.perm || can(t.perm));
  const active = tabs.some((t) => t.value === tab) ? tab : "perfil";
  return (
    <div>
      <PageHeader title="Configurações" />
      <Tabs className="mb-5" value={active} onChange={(v) => nav(`/configuracoes/${v}`)} items={tabs.map((t) => ({ value: t.value, label: t.label }))} />
      {active === "perfil" && <ProfileTab />}
      {active === "estabelecimento" && <EstablishmentTab />}
      {active === "unidades" && <UnitsTab />}
      {active === "equipe" && <TeamTab />}
      {active === "cadastros" && <CatalogsTab />}
      {active === "alertas" && <AlertPrefsTab />}
      {active === "auditoria" && <AuditTab />}
      {active === "integracoes" && <IntegrationsTab />}
    </div>
  );
}
