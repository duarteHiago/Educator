"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

interface UserInfo {
  name: string;
  email: string;
}

interface TokenInfo {
  key_alias: string;
  masked_key: string;
  hostname: string | null;
  is_active: boolean;
  generated_at: string;
  last_used_at: string | null;
}

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [token, setToken] = useState<TokenInfo | null | undefined>(undefined); // undefined = loading
  const [newKey, setNewKey] = useState<string | null>(null);   // chave completa — exibida só uma vez
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      // verifica sessão
      const meRes = await fetch("/api/auth/me", { credentials: "include" });
      if (!meRes.ok) { router.replace("/login"); return; }
      setUser(await meRes.json());

      // carrega token atual
      const tokRes = await fetch("/api/tokens/me", { credentials: "include" });
      if (tokRes.ok) {
        const data = await tokRes.json();
        setToken(data);   // null = nenhum token ainda
      }
    }
    load();
  }, [router]);

  async function generateToken() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/tokens/generate", {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail ?? "Erro ao gerar token");
        return;
      }
      const data = await res.json();
      setNewKey(data.full_key);   // exibido uma única vez
      // recarrega info do token (agora mascarado)
      const tokRes = await fetch("/api/tokens/me", { credentials: "include" });
      if (tokRes.ok) setToken(await tokRes.json());
    } finally {
      setLoading(false);
    }
  }

  async function revokeToken() {
    if (!confirm("Isso invalidará o token atual. O educator.exe vai parar de funcionar até você gerar um novo. Continuar?")) return;
    setLoading(true);
    setError("");
    try {
      await fetch("/api/tokens/revoke", { method: "POST", credentials: "include" });
      setToken(null);
      setNewKey(null);
    } finally {
      setLoading(false);
    }
  }

  async function copyKey(key: string) {
    await navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    router.replace("/login");
  }

  if (!user || token === undefined) {
    return (
      <div className="min-h-screen flex items-center justify-center text-[#444] text-sm">
        Carregando...
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <Link href="/" className="font-mono font-bold text-white tracking-widest">EDUCATOR</Link>
        <div className="flex items-center gap-4">
          <span className="text-[#555] text-sm hidden sm:block">{user.email}</span>
          <button onClick={logout} className="btn-ghost text-sm py-2 px-4">Sair</button>
        </div>
      </nav>

      <main className="flex-1 max-w-2xl mx-auto w-full px-6 py-12">
        <h1 className="text-2xl font-bold text-white mb-1">
          Olá, {user.name.split(" ")[0]}
        </h1>
        <p className="text-[#555] text-sm mb-10">Gerencie seu token de acesso ao Educator.</p>

        {/* Token card */}
        <div className="card p-8 mb-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-white font-bold">Token de Acesso</h2>
            {token && (
              <span className={`text-xs px-2 py-0.5 rounded-full border ${
                token.hostname
                  ? "border-green/30 text-[#00ff99] bg-[#00ff9910]"
                  : "border-yellow-500/30 text-yellow-400 bg-yellow-500/10"
              }`}>
                {token.hostname ? "Vinculado" : "Não vinculado"}
              </span>
            )}
          </div>

          {/* Chave nova — exibida apenas uma vez após geração */}
          {newKey && (
            <div className="mb-6 p-4 rounded border border-[#00bfff33] bg-[#00bfff08]">
              <p className="text-xs text-[#00bfff] mb-2 tracking-wider">
                ⚠ COPIE AGORA — não será exibido novamente
              </p>
              <div className="flex items-center gap-3">
                <code className="flex-1 font-mono text-sm text-white break-all">{newKey}</code>
                <button
                  onClick={() => copyKey(newKey)}
                  className="btn-ghost text-xs py-1.5 px-3 shrink-0"
                >
                  {copied ? "✓ Copiado" : "Copiar"}
                </button>
              </div>
            </div>
          )}

          {token === null && !newKey ? (
            /* Sem token */
            <div className="text-center py-8">
              <p className="text-[#555] text-sm mb-6">
                Você ainda não gerou seu token de acesso.
              </p>
              <button onClick={generateToken} className="btn-primary" disabled={loading}>
                {loading ? "Gerando..." : "Gerar Token"}
              </button>
            </div>
          ) : token ? (
            /* Token existente */
            <div>
              <div className="mb-4">
                <p className="text-xs text-[#555] mb-1 tracking-wider">TOKEN</p>
                <code className="font-mono text-[#00bfff] text-sm">{token.masked_key}</code>
              </div>
              {token.hostname && (
                <div className="mb-4">
                  <p className="text-xs text-[#555] mb-1 tracking-wider">MÁQUINA VINCULADA</p>
                  <code className="font-mono text-sm text-[#888]">{token.hostname}</code>
                </div>
              )}
              {token.last_used_at && (
                <div className="mb-6">
                  <p className="text-xs text-[#555] mb-1 tracking-wider">ÚLTIMO USO</p>
                  <span className="text-sm text-[#888]">
                    {new Date(token.last_used_at).toLocaleString("pt-BR")}
                  </span>
                </div>
              )}
              <div className="flex gap-3 pt-4 border-t border-[#1e1e1e]">
                <button
                  onClick={generateToken}
                  className="btn-ghost text-sm py-2"
                  disabled={loading}
                >
                  {loading ? "Aguarde..." : "Gerar novo token"}
                </button>
                <button
                  onClick={revokeToken}
                  className="text-red-400 text-sm hover:text-red-300 transition-colors py-2 px-4"
                  disabled={loading}
                >
                  Revogar
                </button>
              </div>
            </div>
          ) : null}

          {error && (
            <p className="text-red-400 text-sm mt-4">{error}</p>
          )}
        </div>

        {/* Instruções */}
        <div className="card p-6">
          <h3 className="text-white font-bold mb-4">Como usar</h3>
          <ol className="space-y-3 text-sm text-[#666]">
            <li><span className="text-[#00bfff] font-mono mr-2">01</span>Baixe o Educator na página de releases</li>
            <li><span className="text-[#00bfff] font-mono mr-2">02</span>Execute <code className="text-[#888]">setup.bat</code> uma vez para instalar o navegador</li>
            <li><span className="text-[#00bfff] font-mono mr-2">03</span>Abra <code className="text-[#888]">educator.exe</code> — ele pedirá seu CPF, senha do AVA e o token acima</li>
            <li><span className="text-[#00bfff] font-mono mr-2">04</span>Na primeira execução o sistema mapeará suas disciplinas automaticamente</li>
          </ol>
          <div className="mt-5 pt-5 border-t border-[#1e1e1e]">
            <a
              href="https://github.com/duarteHiago/Educator/releases/latest"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary text-sm inline-block"
            >
              Baixar Educator.exe
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}
