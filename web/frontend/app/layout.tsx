import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Educator — Automação Acadêmica",
  description: "Automatize suas atividades do AVA Educ com inteligência artificial.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
