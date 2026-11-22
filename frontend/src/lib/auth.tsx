/** Tipos, contexto e hook de autenticação. O componente AuthProvider fica em ./AuthProvider.tsx. */
import { createContext, useContext } from "react";

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

export type AuthState = {
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

export const AuthContext = createContext<AuthState | null>(null);
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
