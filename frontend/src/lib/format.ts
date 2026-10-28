const brlFmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const numFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const intFmt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const TZ = "America/Sao_Paulo";

export const toNum = (v: unknown) => {
  if (v === null || v === undefined || v === "") return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
};

export const brl = (v: unknown) => brlFmt.format(toNum(v));
export const brlCompact = (v: unknown) => {
  const n = toNum(v);
  if (Math.abs(n) >= 1000) return `R$ ${(n / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  return brlFmt.format(n);
};
export const num = (v: unknown, digits = 3) =>
  new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(toNum(v));
export const qty = (v: unknown, unit?: string) => `${numFmt.format(toNum(v))}${unit ? ` ${unit}` : ""}`;
export const int = (v: unknown) => intFmt.format(toNum(v));
export const pct = (v: unknown, digits = 1) =>
  v === null || v === undefined ? "—" : `${toNum(v).toLocaleString("pt-BR", { maximumFractionDigits: digits })}%`;

function parseDate(v: string | Date) {
  if (v instanceof Date) return v;
  // Datas puras (AAAA-MM-DD) são locais, sem conversão de fuso.
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) {
    const [y, m, d] = v.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(v);
}

export const date = (v?: string | Date | null) =>
  v ? parseDate(v).toLocaleDateString("pt-BR", /^\d{4}-\d{2}-\d{2}$/.test(String(v)) ? {} : { timeZone: TZ }) : "—";
export const dateShort = (v?: string | Date | null) =>
  v ? parseDate(v).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", ...(/^\d{4}-\d{2}-\d{2}$/.test(String(v)) ? {} : { timeZone: TZ }) }) : "—";
export const dateTime = (v?: string | null) =>
  v ? new Date(v).toLocaleString("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
export const time = (v?: string | null) =>
  v ? new Date(v).toLocaleTimeString("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }) : "—";

export function todayISO() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  return parts;
}
export function addDaysISO(iso: string, days: number) {
  const d = parseDate(iso);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function monthStartISO() {
  return todayISO().slice(0, 8) + "01";
}
export function relativeMinutes(mins: number) {
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  return `${h}h${String(mins % 60).padStart(2, "0")}`;
}
/** Aceita "1,5" ou "1.5" vindos de campos de formulário. */
export const parseInput = (v: string) => v.replace(/\s/g, "").replace(",", ".");
