import { createContext, useContext } from "react";

export type ToastApi = { success: (m: string) => void; error: (m: unknown) => void };

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast fora do provider");
  return ctx;
}
