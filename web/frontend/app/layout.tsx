import { headers } from "next/headers";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Educator — Automação Acadêmica",
  description: "Automatize suas atividades do AVA Educ com inteligência artificial.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Calling headers() opts into dynamic rendering — Next.js then reads x-nonce from the request
  // and automatically injects the nonce into its own <script> tags (hydration, bootstrap).
  const _nonce = headers().get("x-nonce");

  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
