import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api, type Page } from "./api";
import { useAuth } from "./auth";
import { useToast } from "@/components/ui/Toast";

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

type Params = Record<string, string | number | boolean | undefined | null>;

/** Consulta escopada pela unidade ativa (a chave inclui a unidade). */
export function useApi<T>(url: string | null, params?: Params, opts: { refetchInterval?: number; enabled?: boolean } = {}) {
  const { unit } = useAuth();
  return useQuery<T>({
    queryKey: [unit?.id, url, params] as QueryKey,
    queryFn: () => api.get<T>(url!, params),
    enabled: !!url && opts.enabled !== false,
    refetchInterval: opts.refetchInterval,
    placeholderData: keepPreviousData,
  });
}

export function usePaged<T>(url: string, params: Params) {
  return useApi<Page<T>>(url, params);
}

/** Mutação com aviso de sucesso/erro e invalidação das consultas. */
export function useAction<TVars, TRes = unknown>(fn: (v: TVars) => Promise<TRes>, opts: { success?: string | ((r: TRes) => string); onSuccess?: (r: TRes) => void } = {}) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation<TRes, Error, TVars>({
    mutationFn: fn,
    onSuccess: (r) => {
      qc.invalidateQueries();
      if (opts.success) toast.success(typeof opts.success === "function" ? opts.success(r) : opts.success);
      opts.onSuccess?.(r);
    },
    onError: (e) => toast.error(e),
  });
}

export type Option = { value: string | number; label: string };

export function useOptions(url: string, labelKey = "name", params?: Params) {
  const q = useApi<unknown>(url, { page_size: 500, ...params });
  const data = q.data as { results?: Record<string, unknown>[] } | Record<string, unknown>[] | undefined;
  const list = (Array.isArray(data) ? data : data?.results) || [];
  return { options: list.map((r) => ({ value: r.id as number, label: String(r[labelKey]) })) as Option[], list, loading: q.isLoading };
}
