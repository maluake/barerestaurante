import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { useAuth, type Me } from "@/lib/auth";
import { Button, Checkbox, FormGrid, Input, Notice } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";

export default function Signup() {
  const { setMe } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ establishment_name: "", unit_name: "", city: "", first_name: "", last_name: "", email: "", username: "", password: "", accept_terms: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    setError("");
    setLoading(true);
    try {
      setMe(await api.post<Me>("/auth/signup/", f));
      nav("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Cadastrar estabelecimento" subtitle="Comece com uma unidade. Você pode adicionar outras depois.">
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="critical">{error}</Notice>}
        <Input label="Nome do estabelecimento" value={f.establishment_name} onChange={set("establishment_name")} error={errors.establishment_name} required />
        <FormGrid>
          <Input label="Nome da unidade" hint="Opcional" value={f.unit_name} onChange={set("unit_name")} />
          <Input label="Cidade" value={f.city} onChange={set("city")} />
          <Input label="Seu nome" value={f.first_name} onChange={set("first_name")} error={errors.first_name} required />
          <Input label="Sobrenome" value={f.last_name} onChange={set("last_name")} />
        </FormGrid>
        <Input label="E-mail" type="email" value={f.email} onChange={set("email")} error={errors.email} required />
        <FormGrid>
          <Input label="Usuário" autoComplete="username" value={f.username} onChange={set("username")} error={errors.username} required />
          <Input label="Senha" type="password" autoComplete="new-password" value={f.password} onChange={set("password")} error={errors.password || errors.non_field_errors} hint="Mínimo de 8 caracteres" required />
        </FormGrid>
        <Checkbox checked={f.accept_terms} onChange={set("accept_terms")}
          label="Aceito os termos de uso e a política de privacidade (LGPD)."
          hint="Coletamos apenas os dados necessários à operação. Você pode exportar seus dados pessoais a qualquer momento." />
        {errors.accept_terms && <p className="text-xs text-red-700">{errors.accept_terms}</p>}
        <Button type="submit" className="w-full" size="lg" loading={loading}>Criar conta</Button>
      </form>
      <p className="mt-6 text-sm text-stone-600">Já tem conta? <Link to="/login" className="link">Entrar</Link></p>
    </AuthLayout>
  );
}
