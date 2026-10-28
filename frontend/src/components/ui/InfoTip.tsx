import * as Tooltip from "@radix-ui/react-tooltip";
import * as Popover from "@radix-ui/react-popover";
import { Info } from "lucide-react";
import type { ReactNode } from "react";

/** Explicação acessível por toque e teclado (popover), usada nos indicadores. */
export function InfoTip({ children, label = "O que é este indicador?" }: { children: ReactNode; label?: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="rounded-full p-0.5 text-stone-400 hover:text-stone-700" aria-label={label}>
        <Info className="h-3.5 w-3.5" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={6} className="z-50 max-w-xs rounded-lg bg-stone-900 px-3 py-2 text-xs leading-relaxed text-white shadow-pop animate-in">
          {children}
          <Popover.Arrow className="fill-stone-900" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function Hint({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <Tooltip.Root delayDuration={200}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content sideOffset={5} className="z-50 max-w-xs rounded-md bg-stone-900 px-2.5 py-1.5 text-xs text-white shadow-pop">
          {content}
          <Tooltip.Arrow className="fill-stone-900" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
