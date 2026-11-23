import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ronda — Governança ITIL para Alertas de Segurança",
  description:
    "Painel operacional de priorização P1–P4, matriz Impacto × Urgência, rastro auditável e simulação de políticas.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-[#F8FAFC] text-[#0F172A] antialiased">{children}</body>
    </html>
  );
}
