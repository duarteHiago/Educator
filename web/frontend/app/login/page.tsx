"use client";
import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",   // cookie httpOnly setado pelo backend
        body: JSON.stringify({ email, password }),
      });

      if (res.ok) {
        router.push("/dashboard");
        return;
      }

      const data = await res.json().catch(() => ({}));
      if (res.status === 429) {
        setError("Muitas tentativas. Aguarde 1 minuto.");
      } else if (res.status === 401) {
        setError("E-mail ou senha incorretos.");
      } else {
        setError(data.detail ?? "Erro inesperado. Tente novamente.");
      }
    } catch {
      setError("Sem conexão com o servidor.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <Link href="/" className="font-mono font-bold text-white tracking-widest text-xl">
            EDUCATOR
          </Link>
          <p className="text-[#555] text-sm mt-2">Acesse sua conta</p>
        </div>

        <form onSubmit={handleSubmit} className="card p-8 flex flex-col gap-5">
          <div>
            <label className="block text-xs text-[#666] mb-2 tracking-wider">E-MAIL</label>
            <input
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="seu@email.com"
              required
              autoComplete="email"
            />
          </div>

          <div>
            <label className="block text-xs text-[#666] mb-2 tracking-wider">SENHA</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              required
              autoComplete="current-password"
              minLength={8}
            />
          </div>

          {error && (
            <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded px-3 py-2">
              {error}
            </div>
          )}

          <button type="submit" className="btn-primary mt-2" disabled={loading}>
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="text-center text-[#444] text-xs mt-6">
          Sem acesso?{" "}
          <a
            href="https://wa.me/SEU_NUMERO"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#00bfff] hover:underline"
          >
            Fale comigo no WhatsApp
          </a>
        </p>
      </div>
    </div>
  );
}
