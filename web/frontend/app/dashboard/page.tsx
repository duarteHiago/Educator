"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/errors";

interface UserInfo { name: string; email: string; }
interface TokenInfo { key_alias: string; masked_key: string; hostname: string | null; is_active: boolean; generated_at: string; last_used_at: string | null; }
interface DashboardStats {
  total_runs: number;
  success_rate: number;
  avg_score_percent: number | null;
  courses_discovered: number;
  activities_total: number;
  credit_used_usd: number;
  credit_limit_usd: number;
  recent_runs: RecentRun[];
}
interface RecentRun {
  execution_id: string;
  cmid: number;
  status: string;
  score_percent: number | null;
  started_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  success: "text-[#00ff99]",
  failed:  "text-red-400",
  running: "text-[#00bfff]",
  pending: "text-[#888]",
};

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser]   = useState<UserInfo | null>(null);
  const [token, setToken] = useState<TokenInfo | null | undefined>(undefined);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [meRes, tokRes] = await Promise.all([
          apiFetch("/api/auth/me"),
          fetch("/api/tokens/me", { credentials: "include" }),
        ]);
        setUser(await meRes.json());
        setToken(tokRes.ok ? await tokRes.json() : null);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) { router.replace("/login"); return; }
      }
      try {
        const statsRes = await apiFetch("/api/dashboard/stats");
        setStats(await statsRes.json());
      } catch { /* stats optional */ }
    }
    load();
  }, [router]);

  async function generateToken() {
    setLoading(true); setError("");
    try {
      const res = await apiFetch("/api/tokens/generate", { method: "POST" });
      const data = await res.json();
      setNewKey(data.full_key);
      const tokRes = await fetch("/api/tokens/me", { credentials: "include" });
      if (tokRes.ok) setToken(await tokRes.json());
    } catch (e) { setError(e instanceof ApiError ? e.message : "Erro ao gerar token."); }
    finally { setLoading(false); }
  }

  async function revokeToken() {
    if (!confirm("Isso invalidará o token atual. Continuar?")) return;
    setLoading(true); setError("");
    try {
      await apiFetch("/api/tokens/revoke", { method: "POST" });
      setToken(null); setNewKey(null);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Erro."); }
    finally { setLoading(false); }
  }

  async function copyKey(key: string) {
    await navigator.clipboard.writeText(key);
    setCopied(true); setTimeout(() => setCopied(false), 2000);
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    router.replace("/login");
  }

  if (!user || token === undefined) {
    return <div className="min-h-screen flex items-center justify-center text-[#444] text-sm">Carregando...</div>;
  }

  const creditPct = stats ? Math.min(100, (stats.credit_used_usd / stats.credit_limit_usd) * 100) : 0;

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-mono font-bold text-white tracking-widest">EDUCATOR</Link>
        <div className="flex items-center gap-2">
          <Link href="/runs" className="btn-ghost text-sm py-2 px-3">Histórico</Link>
          <button onClick={logout} className="btn-ghost text-sm py-2 px-3">Sair</button>
        </div>
      </nav>

      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-12">
        <h1 className="text-2xl font-bold text-white mb-1">Olá, {user.name.split(" ")[0]}</h1>
        <p className="text-[#555] text-sm mb-8">{user.email}</p>

        {/* Stats grid */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
            {[
              { label: "Execuções", value: stats.total_runs },
              { label: "Sucesso", value: `${(stats.success_rate * 100).toFixed(0)}%` },
              { label: "Score médio", value: stats.avg_score_percent != null ? `${stats.avg_score_percent.toFixed(1)}%` : "—" },
            ].map(({ label, value }) => (
              <div key={label} className="card p-4">
                <p className="text-xs text-[#555] mb-1 tracking-wider">{label.toUpperCase()}</p>
                <p className="text-xl font-bold text-white">{value}</p>
              </div>
            ))}
          </div>
        )}

        {/* Credit bar */}
        {stats && (
          <div className="card p-5 mb-6">
            <div className="flex justify-between text-xs text-[#555] mb-2">
              <span>Crédito LLM</span>
              <span>${stats.credit_used_usd.toFixed(3)} / ${stats.credit_limit_usd.toFixed(2)}</span>
            </div>
            <div className="h-1.5 bg-[#1e1e1e] rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${creditPct > 80 ? "bg-red-400" : "bg-[#00bfff]"}`}
                style={{ width: `${creditPct}%` }}
              />
            </div>
          </div>
        )}

        {/* Token card */}
        <div className="card p-8 mb-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-white font-bold">Token de Acesso</h2>
            {token && (
              <span className={`text-xs px-2 py-0.5 rounded-full border ${token.hostname ? "border-green/30 text-[#00ff99] bg-[#00ff9910]" : "border-yellow-500/30 text-yellow-400 bg-yellow-500/10"}`}>
                {token.hostname ? "Vinculado" : "Não vinculado"}
              </span>
            )}
          </div>

          {newKey && (
            <div className="mb-6 p-4 rounded border border-[#00bfff33] bg-[#00bfff08]">
              <p className="text-xs text-[#00bfff] mb-2 tracking-wider">⚠ COPIE AGORA — não será exibido novamente</p>
              <div className="flex items-center gap-3">
                <code className="flex-1 font-mono text-sm text-white break-all">{newKey}</code>
                <button onClick={() => copyKey(newKey)} className="btn-ghost text-xs py-1.5 px-3 shrink-0">
                  {copied ? "✓ Copiado" : "Copiar"}
                </button>
              </div>
            </div>
          )}

          {token === null && !newKey ? (
            <div className="text-center py-8">
              <p className="text-[#555] text-sm mb-6">Você ainda não gerou seu token de acesso.</p>
              <button onClick={generateToken} className="btn-primary" disabled={loading}>
                {loading ? "Gerando..." : "Gerar Token"}
              </button>
            </div>
          ) : token ? (
            <div>
              <div className="mb-4">
                <p className="text-xs text-[#555] mb-1 tracking-wider">TOKEN</p>
                <code className="font-mono text-[#00bfff] text-sm">{token.masked_key}</code>
              </div>
              {token.last_used_at && (
                <div className="mb-6">
                  <p className="text-xs text-[#555] mb-1 tracking-wider">ÚLTIMO USO</p>
                  <span className="text-sm text-[#888]">{new Date(token.last_used_at).toLocaleString("pt-BR")}</span>
                </div>
              )}
              <div className="flex gap-3 pt-4 border-t border-[#1e1e1e]">
                <button onClick={generateToken} className="btn-ghost text-sm py-2" disabled={loading}>
                  {loading ? "Aguarde..." : "Gerar novo token"}
                </button>
                <button onClick={revokeToken} className="text-red-400 text-sm hover:text-red-300 transition-colors py-2 px-4" disabled={loading}>
                  Revogar
                </button>
              </div>
            </div>
          ) : null}

          {error && <p className="text-red-400 text-sm mt-4">{error}</p>}
        </div>

        {/* Recent runs */}
        {stats && stats.recent_runs.length > 0 && (
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-bold">Últimas Execuções</h3>
              <Link href="/runs" className="text-xs text-[#00bfff] hover:underline">Ver tudo</Link>
            </div>
            <div className="space-y-2">
              {stats.recent_runs.map(run => (
                <div key={run.execution_id} className="flex items-center justify-between py-2 border-b border-[#111] last:border-0">
                  <span className="text-sm text-[#888]">cmid={run.cmid}</span>
                  <div className="flex items-center gap-4">
                    {run.score_percent !== null && (
                      <span className={`text-sm font-mono ${run.score_percent >= 60 ? "text-[#00ff99]" : "text-red-400"}`}>
                        {run.score_percent.toFixed(1)}%
                      </span>
                    )}
                    <span className={`text-xs ${STATUS_COLORS[run.status] ?? "text-[#888]"}`}>
                      {run.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
