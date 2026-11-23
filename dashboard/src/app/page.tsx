"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BellOff,
  CheckCircle2,
  GitBranch,
  Play,
  RefreshCw,
  Shield,
  Sliders,
} from "lucide-react";
import {
  buscarDetalhe,
  buscarIncidentes,
  buscarResumo,
  reconhecerIncidenteApi,
} from "@/lib/api";
import {
  DEMO_DETALHES,
  DEMO_METRICAS_BASE,
  simularPrioridadeLocal,
} from "@/lib/demoData";
import type {
  Criticidade,
  DetalheIncidente,
  Incidente,
  Prioridade,
  ResumoMetricas,
  SimulacaoDelta,
} from "@/lib/types";

const BADGE_PRIORIDADE: Record<Prioridade, string> = {
  P1: "bg-red-500/20 text-red-300 border-red-500/40",
  P2: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  P3: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  P4: "bg-slate-600/30 text-slate-300 border-slate-500/40",
};

const COR_BARRA: Record<Prioridade, string> = {
  P1: "bg-red-500",
  P2: "bg-amber-500",
  P3: "bg-sky-500",
  P4: "bg-slate-500",
};

const FORMATO_NUM = new Intl.NumberFormat("pt-BR");

export default function DashboardPage() {
  const [modo, setModo] = useState<"demo" | "api">("demo");
  const [apiUrl, setApiUrl] = useState("http://127.0.0.1:8000");
  const [token, setToken] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erroApi, setErroApi] = useState<string | null>(null);

  const [detalhesDemo, setDetalhesDemo] = useState<DetalheIncidente[]>(DEMO_DETALHES);
  const [metricasDemo, setMetricasDemo] = useState<ResumoMetricas>(DEMO_METRICAS_BASE);

  const [incidentesApi, setIncidentesApi] = useState<Incidente[]>([]);
  const [metricasApi, setMetricasApi] = useState<ResumoMetricas | null>(null);
  const [detalheApi, setDetalheApi] = useState<DetalheIncidente | null>(null);

  const [filtroPrioridade, setFiltroPrioridade] = useState<"TODAS" | Prioridade>("TODAS");
  const [selecionadoId, setSelecionadoId] = useState<string>(DEMO_DETALHES[0].incidente.id);
  const [replayExecutando, setReplayExecutando] = useState(false);

  const [simulacao, setSimulacao] = useState<SimulacaoDelta>({
    critPagamentos: "alta",
    critWeb: "media",
    limiarForcaBruta: 50,
    sudoSempreAlto: false,
  });

  const metricas = modo === "demo" ? metricasDemo : (metricasApi ?? DEMO_METRICAS_BASE);

  const listaIncidentes = useMemo(() => {
    const base =
      modo === "demo" ? detalhesDemo.map((d) => d.incidente) : incidentesApi;
    if (filtroPrioridade === "TODAS") return base;
    return base.filter((inc) => inc.prioridade === filtroPrioridade);
  }, [modo, detalhesDemo, incidentesApi, filtroPrioridade]);

  const detalheAtual = useMemo(() => {
    if (modo === "demo") {
      return (
        detalhesDemo.find((d) => d.incidente.id === selecionadoId) ??
        detalhesDemo[0] ??
        null
      );
    }
    return detalheApi;
  }, [modo, detalhesDemo, detalheApi, selecionadoId]);

  const resultadosSimulacao = useMemo(() => {
    const base =
      modo === "demo" ? detalhesDemo.map((d) => d.incidente) : incidentesApi;
    return base.map((inc) => {
      const sim = simularPrioridadeLocal(inc, simulacao);
      return {
        incidente: inc,
        antes: sim.antes,
        depois: sim.depois,
        mudou: sim.antes !== sim.depois,
      };
    });
  }, [modo, detalhesDemo, incidentesApi, simulacao]);

  async function carregarDaApi(url = apiUrl, tok = token, prio = filtroPrioridade) {
    setCarregando(true);
    setErroApi(null);
    try {
      const [resumo, lista] = await Promise.all([
        buscarResumo(url, tok),
        buscarIncidentes(url, tok, prio),
      ]);
      setMetricasApi(resumo);
      setIncidentesApi(lista);
      if (lista.length > 0) {
        const alvo = lista.find((i) => i.id === selecionadoId)?.id ?? lista[0].id;
        setSelecionadoId(alvo);
        const det = await buscarDetalhe(url, tok, alvo);
        setDetalheApi(det);
      } else {
        setDetalheApi(null);
      }
    } catch (erro) {
      setErroApi(erro instanceof Error ? erro.message : "Falha ao conectar na API");
    } finally {
      setCarregando(false);
    }
  }

  async function selecionarIncidente(id: string) {
    setSelecionadoId(id);
    if (modo === "api") {
      try {
        const det = await buscarDetalhe(apiUrl, token, id);
        setDetalheApi(det);
      } catch (erro) {
        setErroApi(erro instanceof Error ? erro.message : "Erro ao abrir incidente");
      }
    }
  }

  async function reconhecer(id: string) {
    if (modo === "demo") {
      const agora = new Date().toISOString();
      setDetalhesDemo((prev) =>
        prev.map((d) =>
          d.incidente.id === id && d.incidente.estado === "aberto"
            ? {
                ...d,
                incidente: {
                  ...d.incidente,
                  estado: "reconhecido",
                  reconhecido_em: agora,
                },
              }
            : d
        )
      );
      return;
    }
    try {
      const res = await reconhecerIncidenteApi(apiUrl, token, id);
      setIncidentesApi((prev) =>
        prev.map((i) => (i.id === id ? res.incidente : i))
      );
      if (detalheApi?.incidente.id === id) {
        setDetalheApi({ ...detalheApi, incidente: res.incidente });
      }
    } catch (erro) {
      setErroApi(erro instanceof Error ? erro.message : "Erro ao reconhecer");
    }
  }

  function executarReplayDemo() {
    if (modo === "api") {
      void carregarDaApi();
      return;
    }
    setReplayExecutando(true);
    const novoId = `8a1f3d20-replay-${Date.now()}`;
    const agora = new Date().toISOString();
    const novoDetalhe: DetalheIncidente = {
      incidente: {
        id: novoId,
        tenant_id: "demo",
        origem: "wazuh",
        categoria: "negacao_servico",
        ativo: "servidor-pagamentos",
        estado: "aberto",
        prioridade: "P1",
        total_eventos: 18,
        contexto: {
          recorrencia_24h: 18,
          fora_do_horario: false,
          ataque_previo_no_ativo: false,
          confirmado: false,
        },
        aberto_em: agora,
        atualizado_em: agora,
        reconhecido_em: null,
        resolvido_em: null,
      },
      decisoes: [
        {
          id: `dec-${Date.now()}`,
          tenant_id: "demo",
          evento_id: `ev-${Date.now()}`,
          incidente_id: novoId,
          decidido_em: agora,
          decisao: {
            prioridade: "P1",
            impacto: "alto",
            urgencia: "alta",
            ativo: "servidor-pagamentos",
            criticidade: "alta",
            resposta: "PT15M",
            politica_versao: 4,
            prioridade_base: false,
            rastro: {
              resumo:
                "negacao_servico → servidor-pagamentos (criticidade alta) → P1, resposta em 15 min",
              passos: [
                { etapa: "categoria", texto: "negacao_servico (replay russellmitchell)" },
                { etapa: "ativo", texto: "IP 10.0.1.5 → servidor-pagamentos (alta)" },
                { etapa: "impacto", texto: "impacto alto" },
                { etapa: "urgencia", texto: "base alta + recorrencia_24h >= 5 → alta" },
                { etapa: "prioridade", texto: "P1, resposta em 15 min (política v4)" },
              ],
            },
          },
        },
      ],
      eventos: [
        {
          id: `ev-${Date.now()}`,
          tenant_id: "demo",
          origem: "wazuh",
          id_origem: "replay-demo-1",
          categoria: "negacao_servico",
          severidade_origem: 10,
          ip_origem: "203.0.113.99",
          ip_destino: "10.0.1.5",
          ativo: "servidor-pagamentos",
          ocorrido_em: agora,
          evidencias: {
            regra: { id: "31151", descricao: "Replay: flood HTTP no serviço de pagamentos" },
          },
        },
      ],
    };

    setTimeout(() => {
      setDetalhesDemo((prev) => [novoDetalhe, ...prev]);
      setMetricasDemo((prev) => ({
        ...prev,
        total_eventos: prev.total_eventos + 18,
        total_incidentes: prev.total_incidentes + 1,
        incidentes_por_prioridade: {
          ...prev.incidentes_por_prioridade,
          P1: prev.incidentes_por_prioridade.P1 + 1,
        },
        incidentes_por_estado: {
          ...prev.incidentes_por_estado,
          aberto: prev.incidentes_por_estado.aberto + 1,
        },
        notificacoes_por_estado: {
          ...prev.notificacoes_por_estado,
          enviada: (prev.notificacoes_por_estado.enviada ?? 0) + 1,
        },
      }));
      setSelecionadoId(novoId);
      setReplayExecutando(false);
    }, 350);
  }

  const totalPrio = Math.max(
    1,
    metricas.incidentes_por_prioridade.P1 +
      metricas.incidentes_por_prioridade.P2 +
      metricas.incidentes_por_prioridade.P3 +
      metricas.incidentes_por_prioridade.P4
  );

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100">
      {/* Cabeçalho operacional */}
      <header className="border-b border-slate-800/80 bg-[#0b1120]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-sky-500/30 bg-sky-500/15 text-sky-400">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-white">
                Ronda <span className="text-xs font-normal text-sky-400">Governança ITIL</span>
              </h1>
              <p className="text-xs text-slate-400">
                Priorização determinística P1–P4, rastro auditável e controle anti-fadiga
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-slate-700 bg-slate-900 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => {
                  setModo("demo");
                  setErroApi(null);
                }}
                className={`rounded-md px-3 py-1.5 font-medium transition ${
                  modo === "demo"
                    ? "bg-sky-500/20 text-sky-300"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Modo Demo (AIT-ADS)
              </button>
              <button
                type="button"
                onClick={() => {
                  setModo("api");
                  if (token.trim()) void carregarDaApi(apiUrl, token, filtroPrioridade);
                }}
                className={`rounded-md px-3 py-1.5 font-medium transition ${
                  modo === "api"
                    ? "bg-emerald-500/20 text-emerald-300"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                API Conectada
              </button>
            </div>

            {modo === "api" && (
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  placeholder="http://127.0.0.1:8000"
                  className="w-44 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                />
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Token rnd_..."
                  className="w-40 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => void carregarDaApi()}
                  disabled={carregando}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${carregando ? "animate-spin" : ""}`} />
                  Conectar
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={executarReplayDemo}
              disabled={replayExecutando}
              className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-60"
            >
              <Play className="h-3.5 w-3.5" />
              {modo === "demo"
                ? replayExecutando
                  ? "Reproduzindo…"
                  : "Executar Replay"
                : "Atualizar Fila"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {erroApi && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-xs text-red-200">
            {erroApi}
          </div>
        )}

        {/* 1. Painel Executivo (Anti-fadiga) */}
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-[#0e1525] p-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Eventos Ingeridos</span>
              <Activity className="h-4 w-4 text-sky-400" />
            </div>
            <p className="mt-2 text-2xl font-semibold text-white">
              {FORMATO_NUM.format(metricas.total_eventos)}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Wazuh + Suricata normalizados em esquema único
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-[#0e1525] p-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Incidentes Correlacionados</span>
              <GitBranch className="h-4 w-4 text-amber-400" />
            </div>
            <p className="mt-2 text-2xl font-semibold text-white">
              {FORMATO_NUM.format(metricas.total_incidentes)}
            </p>
            <p className="mt-1 text-xs text-emerald-400">
              Redução de {(metricas.taxa_reducao_eventos * 100).toFixed(2)}% sobre eventos brutos
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-[#0e1525] p-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Mensagens Enviadas vs. Suprimidas</span>
              <BellOff className="h-4 w-4 text-emerald-400" />
            </div>
            <p className="mt-2 text-2xl font-semibold text-white">
              {FORMATO_NUM.format(metricas.notificacoes_por_estado.enviada ?? 0)}{" "}
              <span className="text-sm font-normal text-slate-400">
                / {FORMATO_NUM.format(metricas.notificacoes_por_estado.suprimida ?? 0)} suprimidas
              </span>
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Silêncio por origem + agrupamento P2 + resumo P3
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-[#0e1525] p-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Distribuição ITIL (P1–P4)</span>
              <AlertTriangle className="h-4 w-4 text-red-400" />
            </div>
            <div className="mt-3 space-y-1.5">
              {(["P1", "P2", "P3", "P4"] as Prioridade[]).map((p) => {
                const qtd = metricas.incidentes_por_prioridade[p] ?? 0;
                const pct = Math.max(2, Math.round((qtd / totalPrio) * 100));
                return (
                  <div key={p} className="flex items-center gap-2 text-xs">
                    <span className="w-6 font-medium text-slate-300">{p}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
                      <div
                        className={`h-full rounded-full ${COR_BARRA[p]}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-14 text-right tabular-nums text-slate-400">
                      {FORMATO_NUM.format(qtd)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* 2. Fila de Incidentes + Rastro ITIL */}
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="rounded-xl border border-slate-800 bg-[#0e1525] lg:col-span-7">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-5 py-3.5">
              <h2 className="text-sm font-semibold text-white">
                Fila de Incidentes ({listaIncidentes.length})
              </h2>
              <div className="flex items-center gap-1">
                {(["TODAS", "P1", "P2", "P3", "P4"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setFiltroPrioridade(p);
                      if (modo === "api" && token.trim()) {
                        void carregarDaApi(apiUrl, token, p);
                      }
                    }}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                      filtroPrioridade === p
                        ? "bg-sky-500/20 text-sky-300"
                        : "text-slate-400 hover:bg-slate-800 hover:text-white"
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div className="divide-y divide-slate-800/70">
              {listaIncidentes.length === 0 ? (
                <div className="px-5 py-10 text-center text-xs text-slate-400">
                  Nenhum incidente encontrado para o filtro selecionado.
                </div>
              ) : (
                listaIncidentes.map((inc) => {
                  const ativo = inc.id === detalheAtual?.incidente.id;
                  return (
                    <div
                      key={inc.id}
                      onClick={() => void selecionarIncidente(inc.id)}
                      className={`flex cursor-pointer items-center justify-between gap-4 px-5 py-3.5 transition ${
                        ativo ? "bg-sky-500/10" : "hover:bg-slate-900/60"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span
                            className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold ${
                              BADGE_PRIORIDADE[inc.prioridade ?? "P3"]
                            }`}
                          >
                            {inc.prioridade ?? "P3"}
                          </span>
                          <span className="truncate text-sm font-medium text-white">
                            {inc.categoria}
                          </span>
                          <span className="text-xs text-slate-500">· {inc.origem}</span>
                        </div>
                        <p className="mt-1 truncate text-xs text-slate-400">
                          Ativo:{" "}
                          <span className="text-slate-200">{inc.ativo ?? "não identificado"}</span> ·{" "}
                          {inc.total_eventos} evento(s) · recorrência 24h:{" "}
                          {inc.contexto.recorrencia_24h}
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        {inc.estado === "aberto" ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void reconhecer(inc.id);
                            }}
                            className="rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-500/25"
                          >
                            Reconhecer
                          </button>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-800/80 px-2 py-1 text-[11px] text-slate-300">
                            <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                            {inc.estado}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Rastro ITIL do Incidente Selecionado */}
          <div className="rounded-xl border border-slate-800 bg-[#0e1525] p-5 lg:col-span-5">
            <h2 className="text-sm font-semibold text-white">Rastro da Decisão ITIL</h2>
            {!detalheAtual ? (
              <p className="mt-6 text-xs text-slate-400">
                Selecione um incidente na fila para inspecionar o rastro auditável.
              </p>
            ) : (
              <div className="mt-4 space-y-4">
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white">
                      {detalheAtual.incidente.categoria} em{" "}
                      {detalheAtual.incidente.ativo ?? "ativo desconhecido"}
                    </span>
                    <span
                      className={`rounded border px-1.5 py-0.5 font-semibold ${
                        BADGE_PRIORIDADE[detalheAtual.incidente.prioridade ?? "P3"]
                      }`}
                    >
                      {detalheAtual.incidente.prioridade ?? "P3"}
                    </span>
                  </div>
                  <p className="mt-1.5 text-slate-400">
                    Contexto: fora do horário:{" "}
                    <strong className="text-slate-200">
                      {detalheAtual.incidente.contexto.fora_do_horario ? "sim" : "não"}
                    </strong>{" "}
                    · ataque prévio:{" "}
                    <strong className="text-slate-200">
                      {detalheAtual.incidente.contexto.ataque_previo_no_ativo ? "sim" : "não"}
                    </strong>
                  </p>
                </div>

                {detalheAtual.decisoes.map((reg) => (
                  <div key={reg.id} className="space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span>
                        Decisão {reg.decisao.prioridade} · política v
                        {reg.decisao.politica_versao}
                      </span>
                      <span>{new Date(reg.decidido_em).toLocaleTimeString("pt-BR")}</span>
                    </div>
                    <ol className="space-y-1.5 border-l border-slate-700 pl-3">
                      {reg.decisao.rastro.passos.map((passo, idx) => (
                        <li key={idx} className="text-xs">
                          <span className="font-medium text-sky-400">{passo.etapa}:</span>{" "}
                          <span className="text-slate-300">{passo.texto}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}

                {detalheAtual.eventos.length > 0 && (
                  <div className="border-t border-slate-800 pt-3">
                    <p className="text-xs font-medium text-slate-300">
                      Último evento correlacionado ({detalheAtual.eventos[0].origem})
                    </p>
                    <pre className="mt-2 max-h-36 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-[11px] text-slate-300">
                      {JSON.stringify(detalheAtual.eventos[0].evidencias, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* 3. Simulador de Política ("Antes vs. Depois") */}
        <section className="rounded-xl border border-slate-800 bg-[#0e1525] p-5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-4">
            <div className="flex items-center gap-2">
              <Sliders className="h-4 w-4 text-sky-400" />
              <div>
                <h2 className="text-sm font-semibold text-white">
                  Simulador de Política (Antes vs. Depois)
                </h2>
                <p className="text-xs text-slate-400">
                  Teste alterações de criticidade e limiares sem afetar o plantão em produção
                </p>
              </div>
            </div>
            <span className="text-xs text-slate-400">
              Alterações impactam{" "}
              <strong className="text-amber-300">
                {resultadosSimulacao.filter((r) => r.mudou).length}
              </strong>{" "}
              de {resultadosSimulacao.length} incidente(s) na fila
            </span>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
            <label className="space-y-1 text-xs">
              <span className="text-slate-400">Criticidade `servidor-pagamentos`</span>
              <select
                value={simulacao.critPagamentos}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    critPagamentos: e.target.value as Criticidade,
                  }))
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
              >
                <option value="alta">alta</option>
                <option value="media">media</option>
                <option value="baixa">baixa</option>
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className="text-slate-400">Criticidade `servidor-web`</span>
              <select
                value={simulacao.critWeb}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    critWeb: e.target.value as Criticidade,
                  }))
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
              >
                <option value="alta">alta</option>
                <option value="media">media</option>
                <option value="baixa">baixa</option>
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className="text-slate-400">
                Limiar força bruta: <strong>{simulacao.limiarForcaBruta}</strong> falhas/24h
              </span>
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                value={simulacao.limiarForcaBruta}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    limiarForcaBruta: Number(e.target.value),
                  }))
                }
                className="w-full accent-sky-500"
              />
            </label>

            <label className="flex items-center gap-2 pt-5 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={simulacao.sudoSempreAlto}
                onChange={(e) =>
                  setSimulacao((s) => ({ ...s, sudoSempreAlto: e.target.checked }))
                }
                className="h-4 w-4 rounded border-slate-700 bg-slate-900 accent-sky-500"
              />
              Comprometimento sempre urgência alta (pré-A5)
            </label>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {resultadosSimulacao.slice(0, 6).map(({ incidente, antes, depois, mudou }) => (
              <div
                key={incidente.id}
                className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs ${
                  mudou
                    ? "border-amber-500/40 bg-amber-500/10"
                    : "border-slate-800 bg-slate-900/50"
                }`}
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-200">{incidente.categoria}</p>
                  <p className="truncate text-[11px] text-slate-400">
                    {incidente.ativo ?? "sem ativo"}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 font-semibold">
                  <span className={`rounded border px-1.5 py-0.5 ${BADGE_PRIORIDADE[antes]}`}>
                    {antes}
                  </span>
                  <span className="text-slate-500">→</span>
                  <span className={`rounded border px-1.5 py-0.5 ${BADGE_PRIORIDADE[depois]}`}>
                    {depois}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
