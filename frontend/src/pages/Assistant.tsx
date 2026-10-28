import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { AlertTriangle, ArrowUp, Bot, Calculator, Database, Lightbulb } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button, Card, Notice, PageHeader } from "@/components/ui";

type Section = { kind: "fact" | "estimate" | "suggestion" | "warning"; text: string };
type Answer = { intent: string; title: string; sections: Section[]; table: { columns: { key: string; label: string }[]; rows: Record<string, string>[] } | null;
  links: { label: string; path: string }[]; provider: string };
type Turn = { q: string; a?: Answer; error?: string };

const KIND = {
  fact: { label: "Fato", Icon: Database, cls: "bg-sky-50 text-sky-900 ring-sky-200" },
  estimate: { label: "Estimativa", Icon: Calculator, cls: "bg-violet-50 text-violet-900 ring-violet-200" },
  suggestion: { label: "Sugestão", Icon: Lightbulb, cls: "bg-pine-50 text-pine-900 ring-pine-200" },
  warning: { label: "Atenção", Icon: AlertTriangle, cls: "bg-amber-50 text-amber-950 ring-amber-200" },
};

function AnswerView({ a }: { a: Answer }) {
  const nav = useNavigate();
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-stone-900">{a.title}</h3>
      <ul className="space-y-2">
        {a.sections.map((s, i) => {
          const k = KIND[s.kind];
          return (
            <li key={i} className="flex gap-2.5 text-sm">
              <span className={clsx("mt-0.5 inline-flex h-fit shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset", k.cls)}>
                <k.Icon className="h-3 w-3" aria-hidden />{k.label}
              </span>
              <span className="text-stone-700">{s.text}</span>
            </li>
          );
        })}
      </ul>
      {a.table && a.table.rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg ring-1 ring-stone-200">
          <table className="w-full text-xs">
            <thead className="bg-stone-50"><tr>{a.table.columns.map((c) => <th key={c.key} className="px-3 py-2 text-left font-semibold text-stone-500">{c.label}</th>)}</tr></thead>
            <tbody className="divide-y divide-stone-100">
              {a.table.rows.map((r, i) => <tr key={i}>{a.table!.columns.map((c) => <td key={c.key} className="px-3 py-2 align-top text-stone-800">{r[c.key]}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      )}
      {a.links.length > 0 && (
        <div className="flex flex-wrap gap-2">{a.links.map((l) => <Button key={l.path} size="sm" variant="subtle" onClick={() => nav(l.path)}>{l.label}</Button>)}</div>
      )}
    </div>
  );
}

export default function Assistant() {
  const info = useApi<{ examples: string[]; provider: string }>("/assistant/");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [turns]);

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    setQ("");
    setBusy(true);
    setTurns((t) => [...t, { q: question }]);
    try {
      const a = await api.post<Answer>("/assistant/", { question });
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)));
    } catch (e) {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
    }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); ask(q); };

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Assistente do Negócio" description="Pergunte em linguagem natural. As respostas usam os dados registrados e separam fatos, estimativas e sugestões. O assistente apenas consulta: nenhuma compra ou alteração de estoque é feita sem você." />
      <Card className="mb-4">
        {turns.length === 0 ? (
          <div className="py-4 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-pine-50 text-pine-700"><Bot className="h-6 w-6" /></div>
            <p className="text-sm font-medium text-stone-800">Experimente uma destas perguntas</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {info.data?.examples.map((ex) => (
                <button key={ex} onClick={() => ask(ex)} className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-sm text-stone-700 hover:border-pine-300 hover:bg-pine-50">{ex}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {turns.map((t, i) => (
              <div key={i} className="space-y-3">
                <div className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-sm bg-pine-800 px-4 py-2 text-sm text-white">{t.q}</div></div>
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-pine-50 text-pine-700"><Bot className="h-4 w-4" /></div>
                  <div className="min-w-0 flex-1 pt-1">
                    {t.a ? <AnswerView a={t.a} /> : t.error ? <Notice tone="critical">{t.error}</Notice> : <span className="text-sm text-stone-500">Consultando os dados…</span>}
                  </div>
                </div>
              </div>
            ))}
            <div ref={end} />
          </div>
        )}
      </Card>
      <form onSubmit={submit} className="sticky bottom-4 flex gap-2 rounded-2xl bg-white p-2 shadow-pop">
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} placeholder="Ex.: Quais produtos estão perto de acabar?" className="flex-1 bg-transparent px-3 text-sm outline-none" aria-label="Pergunta" />
        <Button type="submit" loading={busy} disabled={!q.trim()} icon={<ArrowUp className="h-4 w-4" />} aria-label="Enviar pergunta">Perguntar</Button>
      </form>
      <p className="mt-3 text-center text-xs text-stone-400">Modo: {info.data?.provider === "rules" ? "regras e consultas ao banco (local)" : info.data?.provider}</p>
    </div>
  );
}
