import type { DetalheIncidente, Incidente, ResumoMetricas } from "./types";

const BASE_PADRAO =
  process.env.NEXT_PUBLIC_RONDA_API_URL?.replace(/\/+$/, "") ?? "http://127.0.0.1:8000";

function headers(token?: string): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token && token.trim()) {
    h.Authorization = `Bearer ${token.trim()}`;
  }
  return h;
}

export async function buscarResumo(baseUrl: string, token: string): Promise<ResumoMetricas> {
  const url = `${(baseUrl || BASE_PADRAO).replace(/\/+$/, "")}/v1/metricas/resumo`;
  const resp = await fetch(url, { headers: headers(token), cache: "no-store" });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao carregar métricas`);
  return resp.json();
}

export async function buscarIncidentes(
  baseUrl: string,
  token: string,
  prioridade?: string
): Promise<Incidente[]> {
  const qs = new URLSearchParams({ limite: "50" });
  if (prioridade && prioridade !== "TODAS") qs.set("prioridade", prioridade);
  const url = `${(baseUrl || BASE_PADRAO).replace(/\/+$/, "")}/v1/incidentes?${qs.toString()}`;
  const resp = await fetch(url, { headers: headers(token), cache: "no-store" });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao listar incidentes`);
  return resp.json();
}

export async function buscarDetalhe(
  baseUrl: string,
  token: string,
  id: string
): Promise<DetalheIncidente> {
  const url = `${(baseUrl || BASE_PADRAO).replace(/\/+$/, "")}/v1/incidentes/${id}`;
  const resp = await fetch(url, { headers: headers(token), cache: "no-store" });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao abrir incidente`);
  return resp.json();
}

export async function reconhecerIncidenteApi(
  baseUrl: string,
  token: string,
  id: string
): Promise<{ reconhecido: boolean; incidente: Incidente }> {
  const url = `${(baseUrl || BASE_PADRAO).replace(/\/+$/, "")}/v1/incidentes/${id}/reconhecer`;
  const resp = await fetch(url, { method: "POST", headers: headers(token) });
  if (!resp.ok) throw new Error(`Erro ${resp.status} ao reconhecer incidente`);
  return resp.json();
}
