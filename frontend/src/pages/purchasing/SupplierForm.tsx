import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAction, useOptions } from "@/lib/hooks";
import { Button, FormGrid, FormSection, Input, Select, Textarea } from "@/components/ui";

export type Supplier = { id: number; name: string; trade_name: string; cnpj: string; contact_name: string; phone: string; whatsapp: string; email: string;
  address: string; neighborhood: string; city: string; state: string; latitude: string | null; longitude: string | null; categories: number[]; category_names: string[];
  min_order_value: string; payment_terms: string; delivery_days: number; delivery_fee: string; quality_rating: number | null; punctuality_rating: number | null;
  notes: string; is_active: boolean; is_demo: boolean; created_at: string; documents: { title: string; reference: string; valid_until: string | null }[] };

const RATING = [1, 2, 3, 4, 5].map((n) => ({ value: n, label: `${n} de 5` }));

export function SupplierForm({ supplier, onDone }: { supplier?: Supplier; onDone: (s: Supplier) => void }) {
  const cats = useOptions("/categories/");
  const [f, setF] = useState({
    name: supplier?.name || "", trade_name: supplier?.trade_name || "", cnpj: supplier?.cnpj || "", contact_name: supplier?.contact_name || "",
    phone: supplier?.phone || "", whatsapp: supplier?.whatsapp || "", email: supplier?.email || "", address: supplier?.address || "",
    neighborhood: supplier?.neighborhood || "", city: supplier?.city || "", state: supplier?.state || "", latitude: supplier?.latitude || "", longitude: supplier?.longitude || "",
    min_order_value: supplier ? String(Number(supplier.min_order_value)) : "0", payment_terms: supplier?.payment_terms || "", delivery_days: String(supplier?.delivery_days ?? 1),
    delivery_fee: supplier ? String(Number(supplier.delivery_fee)) : "0", quality_rating: String(supplier?.quality_rating ?? ""), punctuality_rating: String(supplier?.punctuality_rating ?? ""),
    notes: supplier?.notes || "",
  });
  const [categories, setCategories] = useState<number[]>(supplier?.categories || []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const d = (v: string) => v.replace(",", ".");
  const save = useAction(() => {
    const body = { ...f, categories, latitude: f.latitude || null, longitude: f.longitude || null, min_order_value: d(f.min_order_value) || "0", delivery_fee: d(f.delivery_fee) || "0",
      delivery_days: Number(f.delivery_days) || 0, quality_rating: f.quality_rating ? Number(f.quality_rating) : null, punctuality_rating: f.punctuality_rating ? Number(f.punctuality_rating) : null };
    return supplier ? api.patch<Supplier>(`/suppliers/${supplier.id}/`, body) : api.post<Supplier>("/suppliers/", body);
  }, { success: "Fornecedor salvo.", onSuccess: onDone });
  return (
    <div className="space-y-6">
      <FormSection title="Identificação e contato">
        <FormGrid>
          <Input label="Nome ou razão social" value={f.name} onChange={set("name")} error={errors.name} required />
          <Input label="Nome fantasia" value={f.trade_name} onChange={set("trade_name")} />
          <Input label="CNPJ" hint="Opcional" value={f.cnpj} onChange={set("cnpj")} error={errors.cnpj} />
          <Input label="Pessoa de contato" value={f.contact_name} onChange={set("contact_name")} />
          <Input label="Telefone" value={f.phone} onChange={set("phone")} />
          <Input label="WhatsApp" value={f.whatsapp} onChange={set("whatsapp")} />
          <Input label="E-mail" type="email" value={f.email} onChange={set("email")} error={errors.email} />
        </FormGrid>
      </FormSection>
      <FormSection title="Endereço">
        <FormGrid cols={3}>
          <Input label="Endereço" value={f.address} onChange={set("address")} />
          <Input label="Bairro" value={f.neighborhood} onChange={set("neighborhood")} />
          <Input label="Cidade" value={f.city} onChange={set("city")} />
          <Input label="UF" maxLength={2} value={f.state} onChange={set("state")} />
          <Input label="Latitude" hint="Opcional" value={f.latitude} onChange={set("latitude")} error={errors.latitude} />
          <Input label="Longitude" hint="Opcional" value={f.longitude} onChange={set("longitude")} error={errors.longitude} />
        </FormGrid>
      </FormSection>
      <FormSection title="Condições comerciais">
        <FormGrid cols={4}>
          <Input label="Pedido mínimo (R$)" inputMode="decimal" value={f.min_order_value} onChange={set("min_order_value")} />
          <Input label="Prazo de entrega (dias)" inputMode="numeric" value={f.delivery_days} onChange={set("delivery_days")} />
          <Input label="Taxa de entrega (R$)" inputMode="decimal" value={f.delivery_fee} onChange={set("delivery_fee")} />
          <Input label="Condições de pagamento" placeholder="Ex.: 28 dias" value={f.payment_terms} onChange={set("payment_terms")} />
          <Select label="Qualidade (interna)" value={f.quality_rating} onChange={set("quality_rating")} options={RATING} placeholder="Sem avaliação" error={errors.quality_rating} />
          <Select label="Pontualidade (interna)" value={f.punctuality_rating} onChange={set("punctuality_rating")} options={RATING} placeholder="Sem avaliação" />
        </FormGrid>
        <div>
          <p className="mb-2 text-sm font-medium text-stone-700">Categorias atendidas</p>
          <div className="flex flex-wrap gap-2">{cats.options.map((c) => (
            <button type="button" key={c.value} onClick={() => setCategories((x) => (x.includes(Number(c.value)) ? x.filter((y) => y !== c.value) : [...x, Number(c.value)]))}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${categories.includes(Number(c.value)) ? "bg-pine-800 text-white" : "bg-stone-100 text-stone-700"}`}>{c.label}</button>
          ))}</div>
        </div>
        <Textarea label="Observações e documentos" value={f.notes} onChange={set("notes")} />
      </FormSection>
      <div className="flex justify-end border-t border-stone-100 pt-4">
        <Button loading={save.isPending} onClick={() => { setErrors({}); save.mutate(undefined, { onError: (e) => e instanceof ApiError && setErrors(e.fieldErrors) }); }}>Salvar fornecedor</Button>
      </div>
    </div>
  );
}
