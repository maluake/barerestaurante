import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import clsx from "clsx";
import { AlertCircle, CheckCircle2, X } from "lucide-react";

type ToastItem = { id: number; kind: "success" | "error"; message: string };
const Ctx = createContext<{ success: (m: string) => void; error: (m: unknown) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((kind: ToastItem["kind"], message: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, kind, message }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);
  const success = useCallback((m: string) => push("success", m), [push]);
  const error = useCallback((m: unknown) => push("error", m instanceof Error ? m.message : String(m)), [push]);
  return (
    <Ctx.Provider value={{ success, error }}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:bottom-6 sm:items-end sm:px-6" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={clsx("pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl px-4 py-3 text-sm shadow-pop animate-in",
            t.kind === "success" ? "bg-pine-950 text-white" : "bg-white text-red-900 ring-1 ring-red-200")}>
            {t.kind === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-pine-300" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-700" />}
            <span className="flex-1">{t.message}</span>
            <button onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))} aria-label="Fechar aviso" className="opacity-60 hover:opacity-100"><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast fora do provider");
  return ctx;
}
