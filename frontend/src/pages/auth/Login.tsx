import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { useAuth, type Me } from "@/lib/auth";
import { Button, Input, Notice } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";

export default function Login() {
  const { me, setMe } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  if (me) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      setMe(await api.post<Me>("/auth/login/", { username, password }));
      nav(loc.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível entrar.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Entrar" subtitle="Acesse a gestão do seu estabelecimento.">
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="critical">{error}</Notice>}
        <Input label="Usuário" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        <Input label="Senha" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Button type="submit" className="w-full" size="lg" loading={loading}>Entrar</Button>
      </form>
      <p className="mt-6 text-sm text-stone-600">
        Ainda não tem conta? <Link to="/cadastro" className="link">Cadastre seu estabelecimento</Link>
      </p>
      {import.meta.env.DEV && (
        <div className="mt-8 rounded-lg bg-stone-100 p-3 text-xs text-stone-600">
          <strong>Ambiente local de demonstração:</strong> usuários <code>demo.dono</code>, <code>demo.gerente</code>, <code>demo.estoque</code>,
          {" "}<code>demo.atendente</code>, <code>demo.cozinha</code> · senha <code>Demo@2026</code> (após <code>python manage.py seed_demo</code>).
        </div>
      )}
    </AuthLayout>
  );
}
