import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import clsx from "clsx";
import { useState, type ReactNode } from "react";
import { Button } from "./Button";

export function Modal({ open, onOpenChange, title, description, children, footer, size = "md" }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children: ReactNode;
  footer?: ReactNode; size?: "sm" | "md" | "lg" | "xl";
}) {
  const widths = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl" };
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-stone-950/40 backdrop-blur-[1px]" />
        <Dialog.Content
          className={clsx("fixed inset-x-0 bottom-0 z-50 flex max-h-[92vh] flex-col rounded-t-2xl bg-white shadow-pop animate-in",
            "sm:inset-auto sm:left-1/2 sm:top-1/2 sm:w-[calc(100%-2rem)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl", widths[size])}
        >
          <div className="flex items-start justify-between gap-4 border-b border-stone-200 px-5 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold text-stone-900">{title}</Dialog.Title>
              {description ? <Dialog.Description className="mt-0.5 text-sm text-stone-500">{description}</Dialog.Description>
                : <Dialog.Description className="sr-only">{typeof title === "string" ? title : "Janela"}</Dialog.Description>}
            </div>
            <Dialog.Close className="rounded-md p-1 text-stone-500 hover:bg-stone-100 hover:text-stone-800" aria-label="Fechar">
              <X className="h-5 w-5" />
            </Dialog.Close>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-stone-200 bg-stone-50 px-5 py-3 sm:rounded-b-2xl">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Confirmação para ações importantes; pode exigir um motivo. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirmar", danger, requireReason,
  reasonLabel = "Motivo", onConfirm, loading, children }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: string; description?: ReactNode; confirmLabel?: string;
  danger?: boolean; requireReason?: boolean; reasonLabel?: string; onConfirm: (reason: string) => void; loading?: boolean; children?: ReactNode;
}) {
  const [reason, setReason] = useState("");
  return (
    <Modal open={open} onOpenChange={(v) => { if (!v) setReason(""); onOpenChange(v); }} title={title} size="sm"
      footer={<>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>Voltar</Button>
        <Button variant={danger ? "danger" : "primary"} loading={loading} disabled={requireReason && !reason.trim()}
          onClick={() => onConfirm(reason.trim())}>{confirmLabel}</Button>
      </>}>
      <div className="space-y-4">
        {description && <div className="text-sm text-stone-600">{description}</div>}
        {children}
        {requireReason && (
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-stone-700" htmlFor="confirm-reason">{reasonLabel}</label>
            <textarea id="confirm-reason" className="input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
          </div>
        )}
      </div>
    </Modal>
  );
}
