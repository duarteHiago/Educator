"use client";
import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

function formatCpf(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
  if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

export default function CredentialsPage() {
  const router = useRouter();
  const [cpf, setCpf] = useState("");
  const [avaPassword, setAvaPassword] = useState("");
  const [exists, setExists] = useState<boolean | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    async function checkAuth() {
      const meRes = await fetch("/api/auth/me", { credentials: "include" });
      if (!meRes.ok) { router.replace("/login"); return; }

      const statusRes = await fetch("/api/credentials/me", { credentials: "include" });
      if (statusRes.ok) {
        const data = await statusRes.json();
        setExists(data.exists);
        setUpdatedAt(data.updated_at ?? null);
      }
    }
    checkAuth();
  }, [router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const digits = cpf.replace(/\D/g, "");
    if (digits.length !== 11) {
      setError("CPF deve ter 11 dígitos.");
      return;
    }
    if (exists && !confirm("Isso substituirá as credenciais salvas. Continuar?")) return;

    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const res = await fetch("/api/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ cpf: digits, ava_password: avaPassword }),
      });
      if (res.ok) {
        const data = await res.json();
        setExists(true);
        setUpdatedAt(data.updated_at);
        setAvaPassword("");
        setCpf("");
        setSuccess("Credenciais salvas com sucesso.");
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Erro ao salvar credenciais.");
      }
    } catch {
      setError("Sem conexão com o servidor.");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remover as credenciais salvas? Execuções agendadas serão canceladas.")) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await fetch("/api/credentials", { method: "DELETE", credentials: "include" });
      setExists(false);
      setUpdatedAt(null);
      setSuccess("Credenciais removidas.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-mono font-bold text-white tracking-widest">EDUCATOR</Link>
        <Link href="/dashboard" className="btn-ghost text-sm py-2 px-4">Dashboard</Link>
      </nav>

      <main className="flex-1 max-w-lg mx-auto w-full px-6 py-12">
        <h1 className="text-2xl font-bold text-white mb-1">Credenciais AVA</h1>
        <p className="text-[#555] text-sm mb-8">
          Seu CPF e senha do portal são armazenados criptografados e usados apenas para automação.
        </p>

        {/* Status badge */}
        {exists !== null && (
          <div className={`mb-6 px-4 py-3 rounded border text-sm ${
            exists
              ? "border-green/30 text-[#00ff99] bg-[#00ff9910]"
              : "border-[#333] text-[#666] bg-[#111]"
          }`}>
            {exists
              ? `✓ Credenciais configuradas${updatedAt ? ` — atualizado ${new Date(updatedAt).toLocaleString("pt-BR")}` : ""}`
              : "Nenhuma credencial salva."}
          </div>
        )}

        <div className="card p-8">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div>
              <label className="block text-xs text-[#666] mb-2 tracking-wider">CPF</label>
              <input
                type="text"
                inputMode="numeric"
                className="input"
                value={cpf}
                onChange={(e) => setCpf(formatCpf(e.target.value))}
                placeholder="000.000.000-00"
                required
                autoComplete="off"
              />
            </div>

            <div>
              <label className="block text-xs text-[#666] mb-2 tracking-wider">SENHA DO AVA</label>
              <input
                type="password"
                className="input"
                value={avaPassword}
                onChange={(e) => setAvaPassword(e.target.value)}
                placeholder="Sua senha do portal AVA Educ"
                required
                minLength={4}
                autoComplete="new-password"
              />
            </div>

            {error && (
              <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded px-3 py-2">
                {error}
              </div>
            )}
            {success && (
              <div className="text-[#00ff99] text-sm bg-[#00ff9910] border border-green/20 rounded px-3 py-2">
                {success}
              </div>
            )}

            <button type="submit" className="btn-primary mt-2" disabled={loading}>
              {loading ? "Salvando..." : exists ? "Atualizar Credenciais" : "Salvar Credenciais"}
            </button>
          </form>

          {exists && (
            <div className="mt-6 pt-6 border-t border-[#1e1e1e]">
              <button
                onClick={handleDelete}
                className="text-red-400 text-sm hover:text-red-300 transition-colors"
                disabled={loading}
              >
                Remover credenciais salvas
              </button>
            </div>
          )}
        </div>

        <p className="text-xs text-[#444] mt-6 text-center">
          Suas credenciais são criptografadas com AES-128 antes de armazenar.
          Nenhum dado trafega em texto claro.
        </p>
      </main>
    </div>
  );
}
