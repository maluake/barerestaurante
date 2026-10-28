import { useMemo, useState, type ReactNode } from "react";
import clsx from "clsx";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Search } from "lucide-react";
import { Skeleton, EmptyState, ErrorState } from "./States";

export type Column<T> = {
  key: string;
  header: ReactNode;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  /** Valor usado na ordenação no cliente (padrão: row[key]). */
  sortValue?: (row: T) => string | number;
  className?: string;
  hideOnMobile?: boolean;
};

export function DataTable<T extends { id?: number | string }>({
  columns, rows, loading, error, onRetry, empty, onRowClick, sort, onSortChange, footer, rowClassName, dense,
}: {
  columns: Column<T>[]; rows: T[] | undefined; loading?: boolean; error?: unknown; onRetry?: () => void;
  empty?: ReactNode; onRowClick?: (row: T) => void;
  /** Ordenação controlada pelo servidor, no formato DRF ("campo" ou "-campo"). */
  sort?: string; onSortChange?: (s: string) => void; footer?: ReactNode; rowClassName?: (row: T) => string | undefined; dense?: boolean;
}) {
  const [localSort, setLocalSort] = useState<string>("");
  const activeSort = onSortChange ? sort || "" : localSort;
  const sorted = useMemo(() => {
    if (!rows || onSortChange || !localSort) return rows;
    const desc = localSort.startsWith("-");
    const key = localSort.replace(/^-/, "");
    const col = columns.find((c) => c.key === key);
    const get = (r: T) => (col?.sortValue ? col.sortValue(r) : (r as Record<string, unknown>)[key]);
    return [...rows].sort((a, b) => {
      const va = get(a), vb = get(b);
      const na = Number(va), nb = Number(vb);
      const cmp = Number.isFinite(na) && Number.isFinite(nb) && va !== "" && vb !== "" ? na - nb : String(va ?? "").localeCompare(String(vb ?? ""), "pt-BR");
      return desc ? -cmp : cmp;
    });
  }, [rows, localSort, columns, onSortChange]);

  const toggle = (key: string) => {
    const next = activeSort === key ? `-${key}` : activeSort === `-${key}` ? "" : key;
    if (onSortChange) onSortChange(next);
    else setLocalSort(next);
  };

  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  const pad = dense ? "px-3 py-2" : "px-4 py-3";
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-full text-sm">
        <thead>
          <tr className="border-b border-stone-200 bg-stone-50/80">
            {columns.map((c) => {
              const dir = activeSort === c.key ? "asc" : activeSort === `-${c.key}` ? "desc" : null;
              return (
                <th key={c.key} scope="col" aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : undefined}
                  className={clsx("whitespace-nowrap text-xs font-semibold text-stone-500", pad, c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "text-left", c.hideOnMobile && "hidden md:table-cell")}>
                  {c.sortable ? (
                    <button className={clsx("inline-flex items-center gap-1 hover:text-stone-900", c.align === "right" && "flex-row-reverse")} onClick={() => toggle(c.key)}>
                      {c.header}
                      {dir === "asc" ? <ArrowUp className="h-3 w-3" /> : dir === "desc" ? <ArrowDown className="h-3 w-3" /> : <ChevronsUpDown className="h-3 w-3 opacity-40" />}
                    </button>
                  ) : c.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {loading && !rows
            ? Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>{columns.map((c) => <td key={c.key} className={pad}><Skeleton className="h-4 w-full max-w-[160px]" /></td>)}</tr>
              ))
            : sorted?.map((row, i) => (
                <tr key={row.id ?? i} onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={clsx(onRowClick && "cursor-pointer hover:bg-stone-50", rowClassName?.(row))}>
                  {columns.map((c) => (
                    <td key={c.key} className={clsx(pad, "align-middle text-stone-800", c.align === "right" && "num text-right", c.align === "center" && "text-center", c.hideOnMobile && "hidden md:table-cell", c.className)}>
                      {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
        {footer}
      </table>
      {!loading && sorted && sorted.length === 0 && (empty || <EmptyState title="Nada por aqui" description="Nenhum registro encontrado com os filtros atuais." compact />)}
    </div>
  );
}

export function Pagination({ page, count, pageSize = 25, onChange }: { page: number; count: number; pageSize?: number; onChange: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count <= pageSize) return count ? <div className="px-4 py-3 text-xs text-stone-500">{count} registro(s)</div> : null;
  return (
    <div className="flex items-center justify-between border-t border-stone-100 px-4 py-3 text-xs text-stone-500">
      <span>{count} registros · página {page} de {pages}</span>
      <div className="flex gap-1">
        <button className="rounded-md p-1.5 hover:bg-stone-100 disabled:opacity-40" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Página anterior"><ChevronLeft className="h-4 w-4" /></button>
        <button className="rounded-md p-1.5 hover:bg-stone-100 disabled:opacity-40" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Próxima página"><ChevronRight className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder = "Buscar…", className }: { value: string; onChange: (v: string) => void; placeholder?: string; className?: string }) {
  return (
    <div className={clsx("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder} className="input pl-9" />
    </div>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-2 border-b border-stone-100 p-3 sm:flex-row sm:flex-wrap sm:items-center">{children}</div>;
}
