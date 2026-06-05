"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/errors";

interface Activity {
  id: string;
  cmid: number;
  course_id: number;
  activity_type: string;
  title: string;
}

interface Course {
  course_id: number;
  course_name: string;
  activities: Activity[];
}

export default function ActivitiesPage() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [runningCmids, setRunningCmids] = useState<Set<number>>(new Set());
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadCourses() {
    try {
      const res = await apiFetch("/api/activities/courses");
      setCourses(await res.json());
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.replace("/login");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadCourses(); }, []);

  async function handleDiscover() {
    setDiscovering(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/api/jobs/discover", { method: "POST" });
      setSuccess("Mapeamento iniciado. Aguarde alguns minutos e recarregue a página.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro ao iniciar mapeamento.");
    } finally {
      setDiscovering(false);
    }
  }

  async function handleRun(cmid: number, courseId: number) {
    setError("");
    setRunningCmids(prev => new Set(prev).add(cmid));
    try {
      await apiFetch("/api/jobs/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cmid, course_id: courseId, mode: "AUTO_MODE" }),
      });
      setSuccess(`Quiz cmid=${cmid} enviado para execução.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro ao iniciar execução.");
    } finally {
      setRunningCmids(prev => { const s = new Set(prev); s.delete(cmid); return s; });
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-mono font-bold text-white tracking-widest">EDUCATOR</Link>
        <div className="flex gap-3">
          <Link href="/dashboard" className="btn-ghost text-sm py-2 px-4">Dashboard</Link>
          <Link href="/runs" className="btn-ghost text-sm py-2 px-4">Histórico</Link>
        </div>
      </nav>

      <main className="flex-1 max-w-3xl mx-auto w-full px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Atividades</h1>
            <p className="text-[#555] text-sm">Cursos e quizzes descobertos na sua conta AVA.</p>
          </div>
          <button onClick={handleDiscover} className="btn-primary text-sm" disabled={discovering}>
            {discovering ? "Mapeando..." : "Mapear Agora"}
          </button>
        </div>

        {error && <div className="mb-4 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded px-3 py-2">{error}</div>}
        {success && <div className="mb-4 text-[#00ff99] text-sm bg-[#00ff9910] border border-green/20 rounded px-3 py-2">{success}</div>}

        {loading ? (
          <p className="text-[#444] text-sm">Carregando...</p>
        ) : courses.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-[#555] text-sm mb-4">Nenhuma atividade mapeada ainda.</p>
            <button onClick={handleDiscover} className="btn-primary" disabled={discovering}>
              {discovering ? "Mapeando..." : "Iniciar Mapeamento"}
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {courses.map(course => (
              <div key={course.course_id} className="card p-0 overflow-hidden">
                <div className="px-6 py-4 border-b border-[#1e1e1e] flex items-center justify-between">
                  <h2 className="text-white font-bold text-sm">{course.course_name}</h2>
                  <span className="text-xs text-[#555]">
                    {course.activities.filter(a => a.activity_type === "quiz").length} quizzes
                  </span>
                </div>
                <div className="divide-y divide-[#111]">
                  {course.activities.filter(a => a.activity_type === "quiz").map(act => (
                    <div key={act.cmid} className="px-6 py-3 flex items-center justify-between gap-4">
                      <span className="text-sm text-[#aaa] truncate flex-1">{act.title}</span>
                      <button
                        onClick={() => handleRun(act.cmid, act.course_id)}
                        disabled={runningCmids.has(act.cmid)}
                        className="btn-ghost text-xs py-1 px-3 shrink-0"
                      >
                        {runningCmids.has(act.cmid) ? "Enviando..." : "Executar"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
