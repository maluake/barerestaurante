import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import clsx from "clsx";
import { Bell, Building2, ChevronDown, FlaskConical, LogOut, Menu, Search, UserRound, X } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { api } from "@/lib/api";
import { PriorityBadge } from "@/components/ui";
import { NAV, allowed } from "./nav";
import { GlobalSearch } from "./GlobalSearch";
import { Logo } from "./Logo";

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth();
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4" aria-label="Navegação principal">
      {NAV.map((g) => {
        const items = g.items.filter((i) => allowed(i, can));
        if (!items.length) return null;
        return (
          <div key={g.label}>
            <div className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-pine-300/70">{g.label}</div>
            <ul className="space-y-0.5">
              {items.map((i) => (
                <li key={i.to}>
                  <NavLink to={i.to} end={i.to === "/"} onClick={onNavigate}
                    className={({ isActive }) => clsx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive ? "bg-white/10 text-white" : "text-pine-100/80 hover:bg-white/5 hover:text-white")}>
                    <i.icon className="h-4 w-4 shrink-0" aria-hidden />
                    {i.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

type Notif = { unread: number; items: { id: number; alert_id: number; title: string; reason: string; priority: string; action_path: string; read: boolean }[] };

function Notifications() {
  const { can } = useAuth();
  const nav = useNavigate();
  const q = useApi<Notif>(can("alerts.view") ? "/notifications/" : null, undefined, { refetchInterval: 60000 });
  if (!can("alerts.view")) return null;
  const unread = q.data?.unread || 0;
  return (
    <Dropdown.Root onOpenChange={(o) => { if (!o && unread) api.post("/notifications/").then(() => q.refetch()); }}>
      <Dropdown.Trigger className="relative rounded-lg p-2 text-stone-600 hover:bg-stone-100" aria-label={`Notificações${unread ? ` (${unread} não lidas)` : ""}`}>
        <Bell className="h-5 w-5" />
        {unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-700 px-1 text-[10px] font-bold text-white">{unread > 9 ? "9+" : unread}</span>}
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={8} className="z-50 w-[min(92vw,380px)] rounded-xl bg-white p-1 shadow-pop animate-in">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="text-sm font-semibold">Notificações</span>
            <button className="link text-xs" onClick={() => nav("/alertas")}>Ver todos os alertas</button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {(q.data?.items || []).length === 0 && <p className="px-3 py-6 text-center text-sm text-stone-500">Nenhuma notificação pendente.</p>}
            {q.data?.items.map((n) => (
              <Dropdown.Item key={n.id} onSelect={() => nav(n.action_path || "/alertas")}
                className={clsx("cursor-pointer rounded-lg px-3 py-2.5 outline-none data-[highlighted]:bg-stone-50", !n.read && "bg-pine-50/50")}>
                <div className="mb-1 flex items-center gap-2"><PriorityBadge priority={n.priority} /></div>
                <div className="text-sm font-medium text-stone-900">{n.title}</div>
                <div className="line-clamp-2 text-xs text-stone-500">{n.reason}</div>
              </Dropdown.Item>
            ))}
          </div>
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

function UnitSwitcher() {
  const { units, unit, switchUnit, membership } = useAuth();
  const nav = useNavigate();
  return (
    <Dropdown.Root>
      <Dropdown.Trigger className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-stone-100">
        <Building2 className="h-4 w-4 shrink-0 text-stone-500" aria-hidden />
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-stone-900">{unit?.name}</span>
          <span className="hidden truncate text-xs text-stone-500 sm:block">{membership?.organization.name}</span>
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-stone-400" />
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="start" sideOffset={6} className="z-50 min-w-[240px] rounded-xl bg-white p-1 shadow-pop animate-in">
          <Dropdown.Label className="px-3 py-1.5 text-xs font-semibold text-stone-500">Unidades</Dropdown.Label>
          {units.map((u) => (
            <Dropdown.Item key={u.id} onSelect={() => { switchUnit(u.id); nav("/"); }}
              className={clsx("cursor-pointer rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-stone-50", u.id === unit?.id && "font-semibold text-pine-800")}>
              {u.name}
            </Dropdown.Item>
          ))}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

function ProfileMenu() {
  const { me, membership, logout } = useAuth();
  const nav = useNavigate();
  return (
    <Dropdown.Root>
      <Dropdown.Trigger className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-stone-100" aria-label="Menu do usuário">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-pine-100 text-sm font-bold text-pine-800">
          {(me?.user.first_name || me?.user.username || "?").slice(0, 1).toUpperCase()}
        </span>
        <span className="hidden text-left lg:block">
          <span className="block text-sm font-semibold leading-tight">{me?.user.full_name}</span>
          <span className="block text-xs text-stone-500">{membership?.role_label}</span>
        </span>
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={6} className="z-50 min-w-[220px] rounded-xl bg-white p-1 shadow-pop animate-in">
          <div className="px-3 py-2 text-xs text-stone-500">{me?.user.username} · {membership?.role_label}</div>
          <Dropdown.Item onSelect={() => nav("/configuracoes/perfil")} className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-stone-50">
            <UserRound className="h-4 w-4" /> Meu perfil e senha
          </Dropdown.Item>
          <Dropdown.Item onSelect={() => logout().then(() => nav("/login"))} className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-800 outline-none data-[highlighted]:bg-red-50">
            <LogOut className="h-4 w-4" /> Sair
          </Dropdown.Item>
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const { membership } = useAuth();
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const side = (
    <div className="flex h-full flex-col bg-pine-950">
      <div className="flex h-16 items-center px-5"><Logo /></div>
      <Sidebar onNavigate={() => setOpen(false)} />
      <div className="border-t border-white/10 px-5 py-3 text-[11px] text-pine-300/60">Plano {membership?.organization.plan === "pro" ? "Profissional" : membership?.organization.plan === "enterprise" ? "Rede" : "Essencial"}</div>
    </div>
  );

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{side}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-stone-950/50" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-in">{side}</div>
          <button className="absolute right-4 top-4 rounded-lg bg-white/10 p-2 text-white" onClick={() => setOpen(false)} aria-label="Fechar menu"><X className="h-5 w-5" /></button>
        </div>
      )}
      <header className="sticky top-0 z-20 flex h-16 items-center gap-2 border-b border-stone-200 bg-white/90 px-3 backdrop-blur sm:px-6">
        <button className="rounded-lg p-2 text-stone-600 hover:bg-stone-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Abrir menu"><Menu className="h-5 w-5" /></button>
        <UnitSwitcher />
        <div className="flex-1" />
        <button onClick={() => setSearchOpen(true)} className="hidden items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 text-sm text-stone-500 hover:border-stone-300 md:flex">
          <Search className="h-4 w-4" /> Buscar produtos, itens, fornecedores… <kbd className="ml-6 rounded border border-stone-300 bg-white px-1.5 text-[10px]">Ctrl K</kbd>
        </button>
        <button onClick={() => setSearchOpen(true)} className="rounded-lg p-2 text-stone-600 hover:bg-stone-100 md:hidden" aria-label="Buscar"><Search className="h-5 w-5" /></button>
        <Notifications />
        <ProfileMenu />
      </header>
      {membership?.organization.is_demo && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-950 sm:px-6">
          <FlaskConical className="h-4 w-4 shrink-0" aria-hidden />
          <span><strong>Ambiente de demonstração.</strong> Todos os dados, fornecedores e preços são fictícios.</span>
        </div>
      )}
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
      <GlobalSearch open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
