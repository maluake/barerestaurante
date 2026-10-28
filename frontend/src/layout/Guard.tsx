import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { EmptyState } from "@/components/ui";

/** Esconde a tela quando o perfil não tem permissão. A proteção real está no backend (403). */
export function Guard({ perms, children }: { perms: string[]; children: ReactNode }) {
  const { can } = useAuth();
  if (perms.length && !perms.some(can)) {
    return <EmptyState icon={<Lock className="h-6 w-6" />} title="Acesso restrito" description="Seu perfil não tem permissão para esta área. Fale com o proprietário do estabelecimento se precisar de acesso." />;
  }
  return <>{children}</>;
}
