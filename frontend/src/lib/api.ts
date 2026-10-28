/** Cliente HTTP da API. Sessão via cookie HttpOnly + token CSRF; unidade ativa no cabeçalho X-Unit-Id. */

export class ApiError extends Error {
  status: number;
  data: unknown;
  fieldErrors: Record<string, string>;
  constructor(status: number, message: string, data: unknown) {
    super(message);
    this.status = status;
    this.data = data;
    this.fieldErrors = extractFieldErrors(data);
  }
}

function extractFieldErrors(data: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (data && typeof data === "object" && !Array.isArray(data)) {
    for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
      if (k === "detail" || k === "code") continue;
      out[k] = Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ") : String(v);
    }
    const d = data as { field?: string; detail?: string };
    if (d.field && d.detail) out[d.field] = d.detail;
  }
  return out;
}

function messageFrom(status: number, data: unknown): string {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.non_field_errors)) return String(d.non_field_errors[0]);
    const first = Object.entries(d)[0];
    if (first) {
      const v = Array.isArray(first[1]) ? first[1][0] : first[1];
      return typeof v === "string" ? v : "Verifique os dados informados.";
    }
  }
  if (status === 403) return "Você não tem permissão para esta ação.";
  if (status === 404) return "Registro não encontrado.";
  if (status >= 500) return "Erro no servidor. Tente novamente em instantes.";
  return "Não foi possível concluir a operação.";
}

let activeUnit: number | null = null;
export const setActiveUnit = (id: number | null) => {
  activeUnit = id;
};
export const getActiveUnit = () => activeUnit;

function csrfToken() {
  const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function ensureCsrf() {
  if (!csrfToken()) await fetch("/api/auth/csrf/", { credentials: "same-origin" });
}

type Params = Record<string, string | number | boolean | undefined | null>;

export function qs(params?: Params) {
  if (!params) return "";
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function request<T = unknown>(
  method: string,
  url: string,
  body?: unknown,
  opts: { params?: Params; headers?: Record<string, string>; raw?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(opts.headers || {}) };
  if (activeUnit) headers["X-Unit-Id"] = String(activeUnit);
  const isForm = body instanceof FormData;
  if (method !== "GET") {
    await ensureCsrf();
    headers["X-CSRFToken"] = csrfToken();
    if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`/api${url}${qs(opts.params)}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });
  if (opts.raw) {
    if (!res.ok) throw new ApiError(res.status, messageFrom(res.status, null), null);
    return res as unknown as T;
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (res.status === 403 && data?.detail?.includes("credenciais")) window.dispatchEvent(new Event("mise:unauthorized"));
    throw new ApiError(res.status, messageFrom(res.status, data), data);
  }
  return data as T;
}

export const api = {
  get: <T = unknown>(url: string, params?: Params) => request<T>("GET", url, undefined, { params }),
  post: <T = unknown>(url: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>("POST", url, body ?? {}, { headers }),
  patch: <T = unknown>(url: string, body?: unknown) => request<T>("PATCH", url, body ?? {}),
  put: <T = unknown>(url: string, body?: unknown) => request<T>("PUT", url, body ?? {}),
  del: <T = unknown>(url: string) => request<T>("DELETE", url),
};

export async function downloadFile(url: string, params: Params, filename: string) {
  const res = await request<Response>("GET", url, undefined, { params, raw: true });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function newKey() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };
