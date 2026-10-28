import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAction, useApi, useOptions } from "@/lib/hooks";
import { Button, Checkbox, FormGrid, FormSection, Input, Select, Textarea } from "@/components/ui";
import type { Product, Uom } from "./types";

type Pack = { unit: string; quantity: string; contained_unit: string };

export function ProductForm({ product, onDone }: { product?: Product; onDone: (p: Product) => void }) {
  const uoms = useApi<Uom[]>("/units-of-measure/");
  const cats = useOptions("/categories/");
  const sups = useOptions("/suppliers/", "name", { is_active: true });
  const locs = useOptions("/locations/");
  const [f, setF] = useState({
    name: product?.name || "", sku: product?.sku || "", barcode: product?.barcode || "", brand: product?.brand || "",
    description: product?.description || "", category: String(product?.category ?? ""), unit: String(product?.unit ?? ""),
    min_stock: product?.min_stock ? String(Number(product.min_stock)) : "", ideal_stock: product?.ideal_stock ? String(Number(product.ideal_stock)) : "",
    max_stock: product?.max_stock ? String(Number(product.max_stock)) : "", default_location: String(product?.default_location ?? ""),
    main_supplier: String(product?.main_supplier ?? ""), is_perishable: product?.is_perishable ?? false,
    shelf_life_days: product?.shelf_life_days ? String(product.shelf_life_days) : "",
  });
  const [packs, setPacks] = useState<Pack[]>((product?.packagings || []).map((p) => ({ unit: String(p.unit), quantity: String(Number(p.quantity)), contained_unit: String(p.contained_unit) })));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const all = uoms.data || [];
  const stockUnits = all.filter((u) => u.dimension !== "package" || u.code === "pct").map((u) => ({ value: u.id, label: `${u.code} — ${u.name}` }));
  const packUnits = all.filter((u) => u.dimension === "package").map((u) => ({ value: u.id, label: u.name }));
  const innerUnits = all.filter((u) => u.dimension !== "package").map((u) => ({ value: u.id, label: u.code }));
  const dec = (v: string) => (v ? v.replace(",", ".") : null);

  const save = useAction(() => {
    const body = {
      ...f, category: f.category || null, unit: Number(f.unit), default_location: f.default_location || null, main_supplier: f.main_supplier || null,
      min_stock: dec(f.min_stock) || "0", ideal_stock: dec(f.ideal_stock) || "0", max_stock: dec(f.max_stock), shelf_life_days: f.shelf_life_days || null,
      packagings: packs.filter((p) => p.unit && p.quantity && p.contained_unit).map((p) => ({ unit: Number(p.unit), quantity: dec(p.quantity), contained_unit: Number(p.contained_unit) })),
    };
    return product ? api.patch<Product>(`/products/${product.id}/`, body) : api.post<Product>("/products/", body);
  }, { success: product ? "Produto atualizado." : "Produto cadastrado.", onSuccess: onDone });

  const submit = () => { setErrors({}); save.mutate(undefined, { onError: (e) => e instanceof ApiError && setErrors(e.fieldErrors) }); };

  return (
    <div className="space-y-6">
      <FormSection title="Identificação">
        <FormGrid>
          <Input label="Nome" value={f.name} onChange={set("name")} error={errors.name} required />
          <Input label="Código interno" value={f.sku} onChange={set("sku")} error={errors.sku} required />
          <Select label="Categoria" value={f.category} onChange={set("category")} options={cats.options} placeholder="Sem categoria" />
          <Input label="Marca" value={f.brand} onChange={set("brand")} />
          <Input label="Código de barras" hint="Opcional" value={f.barcode} onChange={set("barcode")} />
          <Select label="Fornecedor principal" value={f.main_supplier} onChange={set("main_supplier")} options={sups.options} placeholder="Nenhum" />
        </FormGrid>
        <Textarea label="Descrição" value={f.description} onChange={set("description")} rows={2} />
      </FormSection>
      <FormSection title="Estoque" description="Quantidades na unidade de estoque. O sistema usa mínimo e ideal para alertas e para a lista de compras.">
        <FormGrid cols={4}>
          <Select label="Unidade de estoque" value={f.unit} onChange={set("unit")} options={stockUnits} placeholder="Selecione" error={errors.unit} required />
          <Input label="Estoque mínimo" inputMode="decimal" value={f.min_stock} onChange={set("min_stock")} error={errors.min_stock} />
          <Input label="Estoque ideal" inputMode="decimal" value={f.ideal_stock} onChange={set("ideal_stock")} error={errors.ideal_stock} />
          <Input label="Capacidade máxima" hint="Opcional" inputMode="decimal" value={f.max_stock} onChange={set("max_stock")} error={errors.max_stock} />
        </FormGrid>
        <FormGrid cols={3}>
          <Select label="Local de armazenamento" value={f.default_location} onChange={set("default_location")} options={locs.options} placeholder="Não definido" />
          <div className="flex items-end pb-2"><Checkbox label="Produto perecível" hint="Exige validade no recebimento" checked={f.is_perishable} onChange={set("is_perishable")} /></div>
          <Input label="Validade típica (dias)" inputMode="numeric" value={f.shelf_life_days} onChange={set("shelf_life_days")} hint="Limita sugestões de compra para evitar perdas" />
        </FormGrid>
      </FormSection>
      <FormSection title="Embalagens de compra" description="Defina quanto cada embalagem contém. Sem este cadastro, o sistema não converte caixas, pacotes ou fardos.">
        {packs.map((p, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-stone-500">1</span>
            <Select className="w-36" value={p.unit} onChange={(e) => setPacks(packs.map((x, j) => (j === i ? { ...x, unit: e.target.value } : x)))} options={packUnits} placeholder="Embalagem" aria-label="Embalagem" />
            <span className="text-sm text-stone-500">=</span>
            <Input className="w-24" inputMode="decimal" value={p.quantity} onChange={(e) => setPacks(packs.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} aria-label="Quantidade" />
            <Select className="w-24" value={p.contained_unit} onChange={(e) => setPacks(packs.map((x, j) => (j === i ? { ...x, contained_unit: e.target.value } : x)))} options={innerUnits} placeholder="un." aria-label="Unidade contida" />
            <button className="p-2 text-stone-400 hover:text-red-700" onClick={() => setPacks(packs.filter((_, j) => j !== i))} aria-label="Remover embalagem"><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
        {errors.packagings && <p className="text-xs text-red-700">{errors.packagings}</p>}
        <Button variant="ghost" size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setPacks([...packs, { unit: "", quantity: "", contained_unit: f.unit }])}>Adicionar embalagem</Button>
      </FormSection>
      <div className="flex justify-end gap-2 border-t border-stone-100 pt-4">
        <Button loading={save.isPending} onClick={submit}>{product ? "Salvar alterações" : "Cadastrar produto"}</Button>
      </div>
    </div>
  );
}
