import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ronda — Governança ITIL para Alertas de Segurança",
  description:
    "Painel operacional de priorização P1–P4, rastro de decisão e simulação de políticas.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
