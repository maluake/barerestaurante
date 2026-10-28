import type { ReactNode } from "react";
import { Logo } from "@/layout/Logo";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col justify-center px-4 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-10"><Logo dark /></div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-stone-500">{subtitle}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-pine-950 lg:block">
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "radial-gradient(#fff 1px, transparent 1px)", backgroundSize: "22px 22px" }} />
        <div className="relative flex h-full flex-col justify-end p-14 text-pine-50">
          <p className="max-w-md text-3xl font-bold leading-tight text-white">Cada ingrediente no lugar. Cada número com significado.</p>
          <ul className="mt-8 max-w-md space-y-3 text-sm text-pine-100/80">
            <li>• Estoque por lote com validade e consumo FEFO</li>
            <li>• Baixa automática pela ficha técnica, sem duplicidade</li>
            <li>• Compras pelo menor custo total, não só o menor preço</li>
            <li>• Alertas e recomendações a partir dos seus dados reais</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
