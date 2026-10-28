import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, Clock, Maximize2, Minimize2, RefreshCw, Wifi, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeMinutes, time } from "@/lib/format";
import { Badge, Button, EmptyState, PageHeader } from "@/components/ui";
import type { Order } from "@/components/domain/types";
import { OrderActions } from "./OrderActions";

type Board = { version: string; changed: boolean; columns?: { new: Order[]; preparing: Order[]; ready: Order[]; late: number[] }; slow_order_minutes?: number };

/** Atualização incremental: consulta a cada 4 s e só recarrega quando a versão do painel muda. */
function useBoard() {
  const [board, setBoard] = useState<Board | null>(null);
  const [online, setOnline] = useState(true);
  const version = useRef<string>("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const b = await api.get<Board>("/orders/board/", { version: version.current || undefined });
        if (!alive) return;
        setOnline(true);
        if (b.changed) { version.current = b.version; setBoard(b); }
      } catch {
        if (alive) setOnline(false);
      }
    };
    load();
    const id = setInterval(load, 4000);
    const clock = setInterval(() => setTick((t) => t + 1), 30000);
    return () => { alive = false; clearInterval(id); clearInterval(clock); };
  }, []);
  const force = () => { version.current = ""; setTick((t) => t + 1); api.get<Board>("/orders/board/").then((b) => { version.current = b.version; setBoard(b); }); };
  return { board, online, force, tick };
}

function Ticket({ o, slow, manager }: { o: Order; slow: number; manager: boolean }) {
  const minutes = Math.floor((Date.now() - new Date(o.created_at).getTime()) / 60000);
  const late = ["received", "confirmed", "preparing"].includes(o.status) && minutes > slow;
  const kitchenItems = o.items.filter((i) => i.requires_preparation);
  const otherItems = o.items.filter((i) => !i.requires_preparation);
  return (
    <article className={clsx("rounded-xl bg-white p-4 shadow-card", late && "ring-2 ring-red-600")}>
      <header className="mb-3 flex items-start justify-between gap-2">
        <div>
          <div className="text-xl font-extrabold">#{o.number}</div>
          <div className="text-sm font-medium text-stone-600">{o.origin_label}{o.table_label ? ` · ${o.table_label}` : ""}{o.customer_name ? ` · ${o.customer_name}` : ""}</div>
        </div>
        <div className="text-right">
          <div className={clsx("num flex items-center gap-1 text-lg font-bold", late ? "text-red-700" : "text-stone-800")}><Clock className="h-4 w-4" />{relativeMinutes(minutes)}</div>
          <div className="text-xs text-stone-500">desde {time(o.created_at)}</div>
        </div>
      </header>
      {late && <div className="mb-2"><Badge tone="critical" icon={<AlertTriangle className="h-3 w-3" />}>Atrasado (&gt; {slow} min)</Badge></div>}
      <ul className="space-y-1.5">
        {kitchenItems.map((i) => (
          <li key={i.id} className="text-base">
            <span className="font-extrabold">{Number(i.quantity)}×</span> <span className="font-semibold">{i.name}</span>
            {i.notes && <div className="ml-6 text-sm font-semibold text-ember-700">⟶ {i.notes}</div>}
          </li>
        ))}
      </ul>
      {otherItems.length > 0 && <p className="mt-2 text-xs text-stone-500">Bar/balcão: {otherItems.map((i) => `${Number(i.quantity)}× ${i.name}`).join(", ")}</p>}
      {o.notes && <p className="mt-2 rounded-md bg-amber-50 px-2 py-1 text-sm text-amber-950">{o.notes}</p>}
      <div className="mt-4"><OrderActions order={o} size="lg" kitchenOnly={!manager} /></div>
    </article>
  );
}

export default function Kitchen() {
  const { board, online, force } = useBoard();
  const { can } = useAuth();
  const [full, setFull] = useState(false);
  const cols = board?.columns;
  const slow = board?.slow_order_minutes || 25;
  const Column = ({ title, orders, tone }: { title: string; orders: Order[]; tone: string }) => (
    <section className="min-w-0 flex-1">
      <h2 className={clsx("mb-3 flex items-center justify-between rounded-lg px-3 py-2 text-sm font-bold", tone)}>
        {title}<span className="num rounded-full bg-white/70 px-2">{orders.length}</span>
      </h2>
      <div className="space-y-3">{orders.map((o) => <Ticket key={o.id} o={o} slow={slow} manager={can("orders.manage")} />)}</div>
    </section>
  );
  return (
    <div className={clsx(full && "fixed inset-0 z-50 overflow-auto bg-stone-100 p-4")}>
      <PageHeader title="Painel da cozinha" description="Atualiza sozinho a cada poucos segundos, sem recarregar a página."
        actions={<>
          <span className={clsx("flex items-center gap-1 text-xs font-medium", online ? "text-green-800" : "text-red-700")}>
            {online ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}{online ? "Conectado" : "Sem conexão — tentando novamente"}
          </span>
          <Button variant="secondary" size="sm" icon={<RefreshCw className="h-4 w-4" />} onClick={force}>Atualizar</Button>
          <Button variant="secondary" size="sm" icon={full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />} onClick={() => setFull((f) => !f)}>{full ? "Sair da tela cheia" : "Tela cheia"}</Button>
        </>} />
      {!cols ? null : cols.new.length + cols.preparing.length + cols.ready.length === 0 ? (
        <EmptyState title="Nenhum pedido em aberto" description="Novos pedidos aparecem aqui automaticamente." />
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          <Column title="Novos / aguardando" orders={cols.new} tone="bg-sky-100 text-sky-950" />
          <Column title="Em preparo" orders={cols.preparing} tone="bg-amber-100 text-amber-950" />
          <Column title="Prontos para entregar" orders={cols.ready} tone="bg-green-100 text-green-950" />
        </div>
      )}
    </div>
  );
}
