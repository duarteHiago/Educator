"use client";
import Link from "next/link";

const steps = [
  {
    num: "01",
    title: "Receba seu acesso",
    desc: "Entre em contato. Criamos seu login e você acessa o portal para gerar seu token único.",
  },
  {
    num: "02",
    title: "Instale o Educator",
    desc: "Baixe o .exe, execute o setup.bat uma vez e insira seu token. O sistema mapeia suas disciplinas automaticamente.",
  },
  {
    num: "03",
    title: "Execute suas atividades",
    desc: "Selecione a matéria, confirme e deixe a IA responder. Você acompanha o progresso em tempo real.",
  },
];

const reasons = [
  { icon: "⚡", title: "Economize tempo", desc: "Horas de atividades resolvidas em minutos." },
  { icon: "🔒", title: "100% privado", desc: "Seus dados ficam na sua máquina. Credenciais criptografadas localmente." },
  { icon: "🧠", title: "IA real", desc: "Cadeia de modelos com fallback automático por nível de confiança." },
  { icon: "🎓", title: "Nossa causa", desc: "Estudante que trabalha merece tempo pra viver, não só pra copiar conteúdo." },
];

export default function Landing() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-[#1e1e1e] px-6 py-4 flex items-center justify-between">
        <span className="font-mono font-bold text-white tracking-widest">EDUCATOR</span>
        <Link href="/login" className="btn-primary text-sm">
          Entrar
        </Link>
      </nav>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-6 py-24">
        <div className="inline-block px-3 py-1 rounded-full border border-[#00bfff33] text-[#00bfff] text-xs mb-6 tracking-widest">
          AUTOMAÇÃO ACADÊMICA · AVA EDUC
        </div>
        <h1 className="text-5xl md:text-7xl font-bold text-white mb-6 leading-tight glow-cyan">
          Seu tempo
          <br />
          <span className="text-[#00bfff]">vale mais</span>
        </h1>
        <p className="text-[#888] max-w-lg mb-10 text-lg leading-relaxed">
          Educator automatiza suas atividades do AVA Educ usando inteligência artificial.
          Você escolhe o que executar — a IA resolve.
        </p>
        <div className="flex gap-4 flex-wrap justify-center">
          <a
            href="https://wa.me/SEU_NUMERO"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary"
          >
            Quero acesso
          </a>
          <Link href="/login" className="btn-ghost">
            Já tenho conta
          </Link>
        </div>
      </section>

      {/* Como funciona */}
      <section className="px-6 py-20 border-t border-[#1e1e1e]">
        <div className="max-w-4xl mx-auto">
          <p className="text-[#00bfff] text-xs tracking-widest mb-3">COMO FUNCIONA</p>
          <h2 className="text-3xl font-bold text-white mb-12">Três passos. Simples assim.</h2>
          <div className="grid md:grid-cols-3 gap-6">
            {steps.map((s) => (
              <div key={s.num} className="card p-6">
                <div className="text-[#00bfff] font-mono text-sm mb-3">{s.num}</div>
                <h3 className="text-white font-bold mb-2">{s.title}</h3>
                <p className="text-[#666] text-sm leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Por que */}
      <section className="px-6 py-20 border-t border-[#1e1e1e]">
        <div className="max-w-4xl mx-auto">
          <p className="text-[#00bfff] text-xs tracking-widest mb-3">POR QUE USAMOS</p>
          <h2 className="text-3xl font-bold text-white mb-12">Nossa causa</h2>
          <div className="grid md:grid-cols-2 gap-6">
            {reasons.map((r) => (
              <div key={r.title} className="card p-6 flex gap-4">
                <span className="text-2xl">{r.icon}</span>
                <div>
                  <h3 className="text-white font-bold mb-1">{r.title}</h3>
                  <p className="text-[#666] text-sm leading-relaxed">{r.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-20 border-t border-[#1e1e1e] text-center">
        <h2 className="text-3xl font-bold text-white mb-4">Pronto pra começar?</h2>
        <p className="text-[#666] mb-8">
          Acesso por convite. Entre em contato pelo WhatsApp.
        </p>
        <a
          href="https://wa.me/SEU_NUMERO"
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary"
        >
          Falar no WhatsApp
        </a>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#1e1e1e] px-6 py-6 text-center text-[#333] text-xs">
        Educator — uso pessoal e restrito · {new Date().getFullYear()}
      </footer>
    </div>
  );
}
