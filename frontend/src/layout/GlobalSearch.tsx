import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { Boxes, BookOpen, Search, Tags } from "lucide-react";
import { useApi, useDebounced } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import type { Page } from "@/lib/api";
import { NAV, allowed } from "./nav";

type R = { id: number; name: string; sku?: string; city?: string; category_name?: string };

export function GlobalSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [q, setQ] = useState("");
  const term = useDebounced(q.trim(), 250);
  const { can } = useAuth();
  const nav = useNavigate();
  const enabled = open && term.length >= 2;
  const products = useApi<Page<R>>(enabled && can("products.view") ? "/products/" : null, { search: term, page_size: 5 });
  const items = useApi<Page<R>>(enabled && (can("orders.view") || can("recipes.view")) ? "/menu-items/" : null, { search: term, page_size: 5 });
  const sups = useApi<Page<R>>(enabled && can("suppliers.view") ? "/suppliers/" : null, { search: term, page_size: 5 });
  const pages = NAV.flatMap((g) => g.items).filter((i) => allowed(i, can) && term && i.label.toLowerCase().includes(term.toLowerCase()));
  const go = (to: string) => { onOpenChange(false); setQ(""); nav(to); };
  const Section = ({ title, icon, rows, to }: { title: string; icon: React.ReactNode; rows?: R[]; to: (r: R) => string }) =>
    rows && rows.length ? (
      <div className="py-1">
        <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">{title}</div>
        {rows.map((r) => (
          <button key={r.id} onClick={() => go(to(r))} className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-stone-50">
            <span className="text-stone-400">{icon}</span>
            <span className="flex-1 truncate">{r.name}</span>
            <span className="text-xs text-stone-400">{r.sku || r.category_name || r.city}</span>
          </button>
        ))}
      </div>
    ) : null;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-stone-950/40" />
        <Dialog.Content className="fixed left-1/2 top-[10vh] z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 rounded-2xl bg-white shadow-pop animate-in">
          <Dialog.Title className="sr-only">Busca global</Dialog.Title>
          <Dialog.Description className="sr-only">Busque produtos, itens do cardápio, fornecedores e telas</Dialog.Description>
          <div className="flex items-center gap-3 border-b border-stone-200 px-4">
            <Search className="h-5 w-5 text-stone-400" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Digite ao menos 2 letras…" className="h-14 flex-1 bg-transparent text-base outline-none" />
          </div>
          <div className="max-h-[60vh] overflow-y-auto p-2">
            {pages.length > 0 && (
              <div className="py-1">
                <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">Telas</div>
                {pages.map((p) => (
                  <button key={p.to} onClick={() => go(p.to)} className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-stone-50">
                    <p.icon className="h-4 w-4 text-stone-400" /> {p.label}
                  </button>
                ))}
              </div>
            )}
            <Section title="Produtos" icon={<Boxes className="h-4 w-4" />} rows={products.data?.results} to={(r) => `/estoque/produtos/${r.id}`} />
            <Section title="Cardápio" icon={<BookOpen className="h-4 w-4" />} rows={items.data?.results} to={(r) => `/cardapio/${r.id}`} />
            <Section title="Fornecedores" icon={<Tags className="h-4 w-4" />} rows={sups.data?.results} to={(r) => `/compras/fornecedores/${r.id}`} />
            {term.length < 2 && <p className="px-3 py-6 text-center text-sm text-stone-500">Busque por nome, código interno ou cidade.</p>}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
