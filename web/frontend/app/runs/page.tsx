"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/errors";

interface Run {
  id: string;
  execution_id: string;
  cmid: number;
  course_id: number;
  mode: string;
  status: string;
  score_percent: number | null;
  grade_string: string | null;
  questions_total: number;
  questions_answered: number;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  success: "text-[#00ff99] bg-[#00ff9910] border-green/20",
  failed:  "text-red-400 bg-red-400/10 border-red-400/20",
  running: "text-[#00bfff] bg-[#00bfff10] border-[#00bfff33]",
  pending: "text-[#888] bg-[#ffffff08] border-[#333]",
};

const STATUS_LABELS: Record<string, string> = {
  success: "Concluído",
  failed:  "Falhou",
  running: "Executando",
  pending: "Aguardando",
};

export default function RunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/api/runs?limit=50")
      .then(r => r.json())
      .then(setRuns)
      .catch(e => { if (e instanceof ApiError && e.status === 401) router.replace("/login"); })
      .finally(() => setLoading(false));
  }, [router]);

  function fmt(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("pt-BR");
  }

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-mono font-bold text-white tracking-widest">EDUCATOR</Link>
        <div className="flex gap-3">
          <Link href="/dashboard" className="btn-ghost text-sm py-2 px-4">Dashboard</Link>
          <Link href="/activities" className="btn-ghost text-sm py-2 px-4">Atividades</Link>
        </div>
      </nav>

      <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-12">
        <h1 className="text-2xl font-bold text-white mb-1">Histórico de Execuções</h1>
        <p className="text-[#555] text-sm mb-8">Todos os quizzes executados pela plataforma.</p>

        {loading ? (
          <p className="text-[#444] text-sm">Carregando...</p>
        ) : runs.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-[#555] text-sm">Nenhuma execução ainda.</p>
            <Link href="/activities" className="btn-primary mt-4 inline-block text-sm">Ir para Atividades</Link>
          </div>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e1e1e] text-xs text-[#555] uppercase tracking-wider">
                  <th className="px-6 py-3 text-left">Status</th>
                  <th className="px-6 py-3 text-left">Quiz</th>
                  <th className="px-6 py-3 text-left">Score</th>
                  <th className="px-6 py-3 text-left">Modo</th>
                  <th className="px-6 py-3 text-left">Início</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#111]">
                {runs.map(run => (
                  <tr key={run.id} className="hover:bg-[#ffffff04] transition-colors">
                    <td className="px-6 py-4">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_COLORS[run.status] ?? STATUS_COLORS.pending}`}>
                        {STATUS_LABELS[run.status] ?? run.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-[#aaa]">
                      <span className="font-mono text-xs text-[#555]">cmid={run.cmid}</span>
                    </td>
                    <td className="px-6 py-4">
                      {run.score_percent !== null ? (
                        <span className={run.score_percent >= 60 ? "text-[#00ff99]" : "text-red-400"}>
                          {run.score_percent.toFixed(1)}%
                        </span>
                      ) : <span className="text-[#444]">—</span>}
                    </td>
                    <td className="px-6 py-4 text-[#555] text-xs">{run.mode}</td>
                    <td className="px-6 py-4 text-[#555] text-xs">{fmt(run.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
