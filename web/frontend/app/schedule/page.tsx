"use client";
import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/errors";

interface Schedule {
  id: string;
  course_id: number | null;
  cron_expr: string;
  mode: string;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}

const CRON_PRESETS = [
  { label: "Todo dia às 3h", value: "0 3 * * *" },
  { label: "Todo dia às 6h", value: "0 6 * * *" },
  { label: "Seg, Qua e Sex às 2h", value: "0 2 * * 1,3,5" },
  { label: "Todo domingo às 4h", value: "0 4 * * 0" },
];

export default function SchedulePage() {
  const router = useRouter();
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [cron, setCron] = useState("0 3 * * *");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadSchedules() {
    try {
      const res = await apiFetch("/api/schedule");
      setSchedules(await res.json());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadSchedules(); }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cron_expr: cron, mode: "AUTO_MODE" }),
      });
      setSuccess("Agendamento criado.");
      setCron("0 3 * * *");
      await loadSchedules();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro ao criar agendamento.");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(id: string) {
    try {
      await apiFetch(`/api/schedule/${id}`, { method: "PATCH" });
      setSchedules(prev => prev.map(s => s.id === id ? { ...s, is_active: !s.is_active } : s));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro.");
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Remover este agendamento?")) return;
    try {
      await apiFetch(`/api/schedule/${id}`, { method: "DELETE" });
      setSchedules(prev => prev.filter(s => s.id !== id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro.");
    }
  }

  function fmt(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("pt-BR");
  }

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-mono font-bold text-white tracking-widest">EDUCATOR</Link>
        <Link href="/dashboard" className="btn-ghost text-sm py-2 px-4">Dashboard</Link>
      </nav>

      <main className="flex-1 max-w-2xl mx-auto w-full px-6 py-12">
        <h1 className="text-2xl font-bold text-white mb-1">Agendamentos</h1>
        <p className="text-[#555] text-sm mb-8">Execuções automáticas recorrentes para todos os seus cursos.</p>

        {/* Create form */}
        <div className="card p-6 mb-8">
          <h2 className="text-white font-bold mb-4">Novo Agendamento</h2>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs text-[#666] mb-2 tracking-wider">HORÁRIO (PRESET)</label>
              <div className="flex flex-wrap gap-2 mb-3">
                {CRON_PRESETS.map(p => (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setCron(p.value)}
                    className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                      cron === p.value
                        ? "border-[#00bfff] text-[#00bfff] bg-[#00bfff10]"
                        : "border-[#333] text-[#666] hover:border-[#555]"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <label className="block text-xs text-[#666] mb-1 tracking-wider">EXPRESSÃO CRON (CUSTOM)</label>
              <input
                type="text"
                className="input font-mono"
                value={cron}
                onChange={e => setCron(e.target.value)}
                placeholder="0 3 * * *"
              />
            </div>
            {error && <div className="text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded px-3 py-2">{error}</div>}
            {success && <div className="text-[#00ff99] text-sm bg-[#00ff9910] border border-green/20 rounded px-3 py-2">{success}</div>}
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? "Criando..." : "Criar Agendamento"}
            </button>
          </form>
        </div>

        {/* Schedules list */}
        {loading ? (
          <p className="text-[#444] text-sm">Carregando...</p>
        ) : schedules.length === 0 ? (
          <p className="text-[#555] text-sm text-center py-8">Nenhum agendamento configurado.</p>
        ) : (
          <div className="space-y-3">
            {schedules.map(sched => (
              <div key={sched.id} className="card p-5 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <code className="font-mono text-sm text-[#00bfff]">{sched.cron_expr}</code>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${
                      sched.is_active
                        ? "border-green/30 text-[#00ff99] bg-[#00ff9910]"
                        : "border-[#333] text-[#555]"
                    }`}>
                      {sched.is_active ? "Ativo" : "Pausado"}
                    </span>
                  </div>
                  <p className="text-xs text-[#555]">
                    Próxima execução: {fmt(sched.next_run_at)}
                    {sched.last_run_at && ` · Última: ${fmt(sched.last_run_at)}`}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => handleToggle(sched.id)}
                    className="btn-ghost text-xs py-1.5 px-3"
                  >
                    {sched.is_active ? "Pausar" : "Ativar"}
                  </button>
                  <button
                    onClick={() => handleDelete(sched.id)}
                    className="text-red-400 text-xs hover:text-red-300 transition-colors py-1.5 px-2"
                  >
                    Remover
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
