import clsx from "clsx";

export function Tabs<T extends string>({ value, onChange, items, className }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[]; className?: string;
}) {
  return (
    <div role="tablist" className={clsx("flex gap-1 overflow-x-auto border-b border-stone-200", className)}>
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={clsx("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            value === it.value ? "border-pine-700 text-pine-900" : "border-transparent text-stone-500 hover:text-stone-800")}>
          {it.label}
          {it.count !== undefined && <span className={clsx("ml-1.5 rounded-full px-1.5 text-xs", value === it.value ? "bg-pine-100 text-pine-800" : "bg-stone-100 text-stone-600")}>{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string }[] }) {
  return (
    <div className="inline-flex rounded-lg bg-stone-100 p-0.5" role="radiogroup">
      {items.map((it) => (
        <button key={it.value} role="radio" aria-checked={value === it.value} onClick={() => onChange(it.value)}
          className={clsx("rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
            value === it.value ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-800")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}
