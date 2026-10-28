import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setActiveUnit } from "./api";

export type Unit = { id: number; name: string; city: string; code: string; timezone: string; is_active: boolean };
export type Membership = {
  id: number;
  organization: { id: number; name: string; is_demo: boolean; plan: string };
  role: "owner" | "manager" | "stock" | "attendant" | "kitchen";
  role_label: string;
  permissions: string[];
  units: Unit[];
};
export type Me = {
  user: { id: number; username: string; email: string; first_name: string; full_name: string };
  memberships: Membership[];
};

type AuthState = {
  me: Me | null;
  loading: boolean;
  membership: Membership | null;
  unit: Unit | null;
  units: Unit[];
  can: (perm: string) => boolean;
  switchUnit: (id: number) => void;
  refresh: () => Promise<void>;
  setMe: (me: Me | null) => void;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);
const STORAGE_KEY = "mise.unit";

function readStored(): number | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}
function store(id: number) {
  try {
    localStorage.setItem(STORAGE_KEY, String(id));
  } catch {
    /* armazenamento indisponível: segue apenas em memória */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [unitId, setUnitId] = useState<number | null>(readStored());
  const qc = useQueryClient();

  const setMe = useCallback((value: Me | null) => {
    setMeState(value);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/auth/me/"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, [setMe]);

  useEffect(() => {
    refresh();
    const onUnauthorized = () => setMe(null);
    window.addEventListener("mise:unauthorized", onUnauthorized);
    return () => window.removeEventListener("mise:unauthorized", onUnauthorized);
  }, [refresh, setMe]);

  const allUnits = useMemo(() => me?.memberships.flatMap((m) => m.units) ?? [], [me]);
  const unit = useMemo(() => allUnits.find((u) => u.id === unitId) ?? allUnits[0] ?? null, [allUnits, unitId]);
  const membership = useMemo(
    () => me?.memberships.find((m) => m.units.some((u) => u.id === unit?.id)) ?? me?.memberships[0] ?? null,
    [me, unit],
  );
  // Definido de forma síncrona para que as consultas já saiam com a unidade correta.
  setActiveUnit(unit?.id ?? null);

  const switchUnit = useCallback(
    (id: number) => {
      setActiveUnit(id);
      store(id);
      setUnitId(id);
      qc.clear();
    },
    [qc],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout/");
    } finally {
      qc.clear();
      setMe(null);
    }
  }, [qc, setMe]);

  const perms = useMemo(() => new Set(membership?.permissions ?? []), [membership]);
  const can = useCallback((p: string) => perms.has(p), [perms]);

  return (
    <Ctx.Provider value={{ me, loading, membership, unit, units: allUnits, can, switchUnit, refresh, setMe, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
