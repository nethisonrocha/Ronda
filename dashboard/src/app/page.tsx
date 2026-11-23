"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  Bell,
  CheckCircle2,
  GitBranch,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
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

const FORMATO_NUM = new Intl.NumberFormat("pt-BR");

const ESTILO_PRIO: Record<
  Prioridade,
  { badge: string; ponto: string; texto: string; rotulo: string }
> = {
  P1: {
    badge: "bg-red-50 text-red-700 border-red-200",
    ponto: "bg-red-600",
    texto: "text-red-700",
    rotulo: "P1 Crítico",
  },
  P2: {
    badge: "bg-orange-50 text-orange-700 border-orange-200",
    ponto: "bg-orange-500",
    texto: "text-orange-700",
    rotulo: "P2 Alto",
  },
  P3: {
    badge: "bg-amber-50 text-amber-800 border-amber-200",
    ponto: "bg-amber-500",
    texto: "text-amber-700",
    rotulo: "P3 Médio",
  },
  P4: {
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
    ponto: "bg-emerald-600",
    texto: "text-emerald-700",
    rotulo: "P4 Baixo",
  },
};

interface FatiaRosca {
  rotulo: string;
  valor: number;
  cor: string;
}

function GraficoRosca({
  titulo,
  centroValor,
  centroSub,
  fatias,
}: {
  titulo: string;
  centroValor: string;
  centroSub: string;
  fatias: FatiaRosca[];
}) {
  const total = Math.max(
    1,
    fatias.reduce((acc, f) => acc + f.valor, 0)
  );
  const raio = 36;
  const circ = 2 * Math.PI * raio;
  let acumulado = 0;

  return (
    <div className="flex flex-col items-center">
      <p className="mb-3 text-xs font-semibold text-slate-700">{titulo}</p>
      <div className="flex items-center gap-4">
        <div className="relative h-28 w-28 shrink-0">
          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
            <circle
              cx="50"
              cy="50"
              r={raio}
              fill="transparent"
              stroke="#E2E8F0"
              strokeWidth="12"
            />
            {fatias.map((f) => {
              const frac = f.valor / total;
              const dash = frac * circ;
              const offset = -acumulado * circ;
              acumulado += frac;
              if (f.valor <= 0) return null;
              return (
                <circle
                  key={f.rotulo}
                  cx="50"
                  cy="50"
                  r={raio}
                  fill="transparent"
                  stroke={f.cor}
                  strokeWidth="12"
                  strokeDasharray={`${dash} ${circ - dash}`}
                  strokeDashoffset={offset}
                />
              );
            })}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-sm font-bold tabular-nums text-slate-900">
              {centroValor}
            </span>
            <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
              {centroSub}
            </span>
          </div>
        </div>

        <ul className="space-y-1.5 text-xs">
          {fatias.map((f) => {
            const pct = ((f.valor / total) * 100).toFixed(1);
            return (
              <li key={f.rotulo} className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 text-slate-600">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: f.cor }}
                  />
                  {f.rotulo}
                </span>
                <span className="font-semibold tabular-nums text-slate-800">{pct}%</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

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
  const [busca, setBusca] = useState("");
  const [selecionadoId, setSelecionadoId] = useState<string>(DEMO_DETALHES[0].incidente.id);
  const [replayExecutando, setReplayExecutando] = useState(false);
  const [mostrarJson, setMostrarJson] = useState(false);

  const [simulacao, setSimulacao] = useState<SimulacaoDelta>({
    critPagamentos: "alta",
    critWeb: "media",
    limiarForcaBruta: 50,
    sudoSempreAlto: false,
  });

  const metricas = modo === "demo" ? metricasDemo : (metricasApi ?? DEMO_METRICAS_BASE);
  const baseIncidentes = useMemo(
    () => (modo === "demo" ? detalhesDemo.map((d) => d.incidente) : incidentesApi),
    [modo, detalhesDemo, incidentesApi]
  );

  const listaIncidentes = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return baseIncidentes.filter((inc) => {
      if (filtroPrioridade !== "TODAS" && inc.prioridade !== filtroPrioridade) return false;
      if (!q) return true;
      return (
        inc.categoria.toLowerCase().includes(q) ||
        (inc.ativo ?? "").toLowerCase().includes(q) ||
        inc.origem.toLowerCase().includes(q)
      );
    });
  }, [baseIncidentes, filtroPrioridade, busca]);

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

  const topAtivos = useMemo(() => {
    const mapa = new Map<string, { ativo: string; prio: Prioridade; eventos: number }>();
    const ordem: Record<Prioridade, number> = { P1: 1, P2: 2, P3: 3, P4: 4 };
    for (const inc of baseIncidentes) {
      const nome = inc.ativo ?? "sem-ativo";
      const prio = inc.prioridade ?? "P3";
      const atual = mapa.get(nome);
      if (!atual) {
        mapa.set(nome, { ativo: nome, prio, eventos: inc.total_eventos });
      } else {
        atual.eventos += inc.total_eventos;
        if (ordem[prio] < ordem[atual.prio]) atual.prio = prio;
      }
    }
    return Array.from(mapa.values())
      .sort((a, b) => ordem[a.prio] - ordem[b.prio] || b.eventos - a.eventos)
      .slice(0, 6);
  }, [baseIncidentes]);

  const fatiasPrioridade: FatiaRosca[] = [
    { rotulo: "P1 Crítico", valor: metricas.incidentes_por_prioridade.P1 ?? 0, cor: "#DC2626" },
    { rotulo: "P2 Alto", valor: metricas.incidentes_por_prioridade.P2 ?? 0, cor: "#EA580C" },
    { rotulo: "P3 Médio", valor: metricas.incidentes_por_prioridade.P3 ?? 0, cor: "#EAB308" },
    { rotulo: "P4 Baixo", valor: metricas.incidentes_por_prioridade.P4 ?? 0, cor: "#16A34A" },
  ];

  const fatiasOrigem: FatiaRosca[] = useMemo(() => {
    const porCat = new Map<string, number>();
    for (const inc of baseIncidentes) {
      porCat.set(inc.categoria, (porCat.get(inc.categoria) ?? 0) + 1);
    }
    const cores = ["#2563EB", "#EA580C", "#16A34A", "#7C3AED", "#64748B"];
    const itens = Array.from(porCat.entries()).slice(0, 5);
    if (itens.length === 0) {
      return [{ rotulo: "Sem dados", valor: 1, cor: "#CBD5E1" }];
    }
    return itens.map(([cat, valor], idx) => ({
      rotulo: cat,
      valor,
      cor: cores[idx % cores.length],
    }));
  }, [baseIncidentes]);

  const resultadosSimulacao = useMemo(() => {
    return baseIncidentes.map((inc) => {
      const sim = simularPrioridadeLocal(inc, simulacao);
      return {
        incidente: inc,
        antes: sim.antes,
        depois: sim.depois,
        mudou: sim.antes !== sim.depois,
      };
    });
  }, [baseIncidentes, simulacao]);

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
      setIncidentesApi((prev) => prev.map((i) => (i.id === id ? res.incidente : i)));
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
    }, 300);
  }

  const qtdP1 = metricas.incidentes_por_prioridade.P1 ?? 0;
  const qtdP2 = metricas.incidentes_por_prioridade.P2 ?? 0;
  const qtdP3 = metricas.incidentes_por_prioridade.P3 ?? 0;
  const qtdP4 = metricas.incidentes_por_prioridade.P4 ?? 0;

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A]">
      {/* Header corporativo limpo */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0F172A] text-white shadow-sm">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-slate-900">Ronda</h1>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                  ITIL v4
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Governança determinística para priorização de alertas em NOC/SOC
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => {
                  setModo("demo");
                  setErroApi(null);
                }}
                className={`rounded-md px-3 py-1.5 font-medium transition ${
                  modo === "demo"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
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
                    ? "bg-white text-emerald-700 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
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
                  className="w-44 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 focus:border-blue-500 focus:outline-none"
                />
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Token rnd_..."
                  className="w-40 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 focus:border-blue-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => void carregarDaApi()}
                  disabled={carregando}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
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
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60"
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

      <main className="mx-auto max-w-[1400px] space-y-5 px-6 py-6">
        {erroApi && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
            {erroApi}
          </div>
        )}

        {/* 1. Linha de 4 Cards KPI (estilo corporativo com ícone pastel à esquerda) */}
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Eventos Ingeridos</p>
              <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
                {FORMATO_NUM.format(metricas.total_eventos)}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">Wazuh + Suricata eve.json</p>
            </div>
          </div>

          <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-orange-50 text-orange-600">
              <GitBranch className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Incidentes Correlacionados</p>
              <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
                {FORMATO_NUM.format(metricas.total_incidentes)}
              </p>
              <p className="mt-0.5 text-xs font-medium text-emerald-700">
                Redução de {(metricas.taxa_reducao_eventos * 100).toFixed(2)}%
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-purple-50 text-purple-600">
              <Bell className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Notificações Enviadas</p>
              <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
                {FORMATO_NUM.format(metricas.notificacoes_por_estado.enviada ?? 0)}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {FORMATO_NUM.format(metricas.notificacoes_por_estado.suprimida ?? 0)} suprimidas
                anti-fadiga
              </p>
            </div>
          </div>

          <div
            className={`flex items-center gap-4 rounded-xl border p-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)] ${
              qtdP1 > 0
                ? "border-red-200 bg-white"
                : "border-emerald-200 bg-white"
            }`}
          >
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                qtdP1 > 0 ? "bg-red-50 text-red-600" : "bg-emerald-50 text-emerald-600"
              }`}
            >
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Nível de Ação Atual</p>
              <p
                className={`mt-0.5 text-2xl font-bold ${
                  qtdP1 > 0 ? "text-red-600" : "text-emerald-700"
                }`}
              >
                {qtdP1 > 0 ? "P1 Crítico" : "Normal"}
              </p>
              <p className="mt-0.5 text-xs font-medium text-slate-600">
                {FORMATO_NUM.format(qtdP1)} P1 · {FORMATO_NUM.format(qtdP2)} P2 em acompanhamento
              </p>
            </div>
          </div>
        </section>

        {/* 2. Grade Principal (3 colunas como na referência) */}
        <section className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          {/* Coluna Esquerda: Matriz de Calor ITIL 3x3 */}
          <div className="space-y-5 lg:col-span-3">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
              <h2 className="text-sm font-bold text-slate-900">
                Matriz de Calor ITIL
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Impacto × Urgência para priorização determinística
              </p>

              <div className="mt-4">
                <div className="grid grid-cols-4 gap-1.5 text-center text-[11px]">
                  <div />
                  <div className="font-semibold text-slate-500">Baixa</div>
                  <div className="font-semibold text-slate-500">Média</div>
                  <div className="font-semibold text-slate-500">Alta</div>

                  {/* Linha Impacto Alto */}
                  <div className="flex items-center justify-end pr-1.5 font-semibold text-slate-600">
                    Alto
                  </div>
                  <div className="rounded-md bg-amber-400 px-1 py-2.5 font-bold text-slate-950">
                    <div className="text-[10px] font-semibold">P3</div>
                  </div>
                  <div className="rounded-md bg-orange-500 px-1 py-2.5 font-bold text-white">
                    <div className="text-[10px] font-semibold">P2</div>
                    <div className="tabular-nums">{FORMATO_NUM.format(qtdP2)}</div>
                  </div>
                  <div className="rounded-md bg-red-600 px-1 py-2.5 font-bold text-white shadow-sm">
                    <div className="text-[10px] font-semibold">P1</div>
                    <div className="tabular-nums">{FORMATO_NUM.format(qtdP1)}</div>
                  </div>

                  {/* Linha Impacto Médio */}
                  <div className="flex items-center justify-end pr-1.5 font-semibold text-slate-600">
                    Médio
                  </div>
                  <div className="rounded-md bg-emerald-500 px-1 py-2.5 font-bold text-white">
                    <div className="text-[10px] font-semibold">P4</div>
                  </div>
                  <div className="rounded-md bg-amber-400 px-1 py-2.5 font-bold text-slate-950">
                    <div className="text-[10px] font-semibold">P3</div>
                    <div className="tabular-nums">{FORMATO_NUM.format(qtdP3)}</div>
                  </div>
                  <div className="rounded-md bg-orange-500 px-1 py-2.5 font-bold text-white">
                    <div className="text-[10px] font-semibold">P2</div>
                  </div>

                  {/* Linha Impacto Baixo */}
                  <div className="flex items-center justify-end pr-1.5 font-semibold text-slate-600">
                    Baixo
                  </div>
                  <div className="rounded-md bg-emerald-600 px-1 py-2.5 font-bold text-white">
                    <div className="text-[10px] font-semibold">P4</div>
                    <div className="tabular-nums">{FORMATO_NUM.format(qtdP4)}</div>
                  </div>
                  <div className="rounded-md bg-emerald-500 px-1 py-2.5 font-bold text-white">
                    <div className="text-[10px] font-semibold">P4</div>
                  </div>
                  <div className="rounded-md bg-amber-400 px-1 py-2.5 font-bold text-slate-950">
                    <div className="text-[10px] font-semibold">P3</div>
                  </div>
                </div>
                <p className="mt-2 text-center text-[11px] font-medium text-slate-500">
                  Eixo Horizontal: Urgência · Eixo Vertical: Impacto
                </p>
              </div>
            </div>

            {/* Legenda Nível de Prioridade */}
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
              <h3 className="text-xs font-bold uppercase tracking-wide text-slate-700">
                Níveis de Prioridade (SLA)
              </h3>
              <ul className="mt-3 space-y-2.5 text-xs">
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 font-medium text-slate-700">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-600" />
                    P1 Crítico (Imediato · 15 min)
                  </span>
                  <span className="font-bold tabular-nums text-red-700">
                    {FORMATO_NUM.format(qtdP1)}
                  </span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 font-medium text-slate-700">
                    <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
                    P2 Alto (Agrupado · 1 h)
                  </span>
                  <span className="font-bold tabular-nums text-orange-700">
                    {FORMATO_NUM.format(qtdP2)}
                  </span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 font-medium text-slate-700">
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                    P3 Médio (Resumo diário · 24 h)
                  </span>
                  <span className="font-bold tabular-nums text-amber-700">
                    {FORMATO_NUM.format(qtdP3)}
                  </span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 font-medium text-slate-700">
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
                    P4 Baixo (Apenas painel)
                  </span>
                  <span className="font-bold tabular-nums text-emerald-700">
                    {FORMATO_NUM.format(qtdP4)}
                  </span>
                </li>
              </ul>
            </div>
          </div>

          {/* Coluna Central: Distribuição (2 Roscas) + Fila de Incidentes */}
          <div className="space-y-5 lg:col-span-5">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">
                  Distribuição dos Incidentes
                </h2>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                  Base: {FORMATO_NUM.format(metricas.total_incidentes)}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <GraficoRosca
                  titulo="Por Prioridade ITIL"
                  centroValor={FORMATO_NUM.format(metricas.total_incidentes)}
                  centroSub="TOTAL"
                  fatias={fatiasPrioridade}
                />
                <GraficoRosca
                  titulo="Por Categoria na Fila"
                  centroValor={String(baseIncidentes.length)}
                  centroSub="FILA"
                  fatias={fatiasOrigem}
                />
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-5 py-3.5">
                <h2 className="text-sm font-bold text-slate-900">
                  Fila de Incidentes ({listaIncidentes.length})
                </h2>
                <div className="flex flex-wrap items-center gap-1">
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
                      className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                        filtroPrioridade === p
                          ? "bg-blue-600 text-white"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div className="border-b border-slate-100 px-5 py-2.5">
                <div className="relative">
                  <Search className="pointer-events-none absolute top-2 left-2.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    value={busca}
                    onChange={(e) => setBusca(e.target.value)}
                    placeholder="Filtrar por ativo, categoria ou origem..."
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 pr-3 pl-8 text-xs text-slate-800 focus:border-blue-500 focus:bg-white focus:outline-none"
                  />
                </div>
              </div>

              <div className="divide-y divide-slate-100">
                {listaIncidentes.length === 0 ? (
                  <div className="px-5 py-10 text-center text-xs text-slate-500">
                    Nenhum incidente encontrado para o filtro selecionado.
                  </div>
                ) : (
                  listaIncidentes.map((inc) => {
                    const prio = inc.prioridade ?? "P3";
                    const estilo = ESTILO_PRIO[prio];
                    const selecionado = inc.id === detalheAtual?.incidente.id;
                    return (
                      <div
                        key={inc.id}
                        onClick={() => void selecionarIncidente(inc.id)}
                        className={`flex cursor-pointer items-center justify-between gap-3 px-5 py-3 transition ${
                          selecionado ? "bg-blue-50/70" : "hover:bg-slate-50"
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-bold ${estilo.badge}`}
                            >
                              <span className={`h-1.5 w-1.5 rounded-full ${estilo.ponto}`} />
                              {prio}
                            </span>
                            <span className="truncate text-sm font-semibold text-slate-900">
                              {inc.categoria}
                            </span>
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                                inc.origem === "suricata"
                                  ? "bg-orange-50 text-orange-700"
                                  : "bg-blue-50 text-blue-700"
                              }`}
                            >
                              {inc.origem}
                            </span>
                          </div>
                          <p className="mt-1 truncate text-xs text-slate-500">
                            Ativo:{" "}
                            <span className="font-medium text-slate-700">
                              {inc.ativo ?? "não identificado"}
                            </span>{" "}
                            · {inc.total_eventos} evento(s) · rec. 24h:{" "}
                            {inc.contexto.recorrencia_24h}
                          </p>
                        </div>

                        <div className="shrink-0">
                          {inc.estado === "aberto" ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                void reconhecer(inc.id);
                              }}
                              className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                            >
                              Reconhecer
                            </button>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
                              <CheckCircle2 className="h-3 w-3 text-emerald-600" />
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
          </div>

          {/* Coluna Direita: Top Ativos + Rastro Auditável ITIL */}
          <div className="space-y-5 lg:col-span-4">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">
                  Principais Ativos Afetados
                </h2>
                <span className="text-xs font-medium text-slate-400">Eventos</span>
              </div>
              <ul className="mt-3 divide-y divide-slate-100 text-xs">
                {topAtivos.length === 0 ? (
                  <li className="py-4 text-slate-500">Sem ativos registrados.</li>
                ) : (
                  topAtivos.map((item) => (
                    <li
                      key={item.ativo}
                      className="flex items-center justify-between py-2.5"
                    >
                      <span className="flex items-center gap-2 font-medium text-slate-700">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${ESTILO_PRIO[item.prio].ponto}`}
                        />
                        {item.ativo}
                      </span>
                      <span className="font-bold tabular-nums text-slate-900">
                        {FORMATO_NUM.format(item.eventos)}
                      </span>
                    </li>
                  ))
                )}
              </ul>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">Rastro da Decisão ITIL</h2>
                {detalheAtual && (
                  <span
                    className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${
                      ESTILO_PRIO[detalheAtual.incidente.prioridade ?? "P3"].badge
                    }`}
                  >
                    {ESTILO_PRIO[detalheAtual.incidente.prioridade ?? "P3"].rotulo}
                  </span>
                )}
              </div>

              {!detalheAtual ? (
                <p className="mt-4 text-xs text-slate-500">
                  Selecione um incidente na fila para inspecionar o rastro determinístico.
                </p>
              ) : (
                <div className="mt-4 space-y-4">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
                    <p className="font-semibold text-slate-900">
                      {detalheAtual.incidente.categoria} em{" "}
                      {detalheAtual.incidente.ativo ?? "ativo desconhecido"}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                      <span
                        className={`rounded px-2 py-0.5 font-medium ${
                          detalheAtual.incidente.contexto.fora_do_horario
                            ? "bg-amber-100 text-amber-800"
                            : "bg-slate-200 text-slate-600"
                        }`}
                      >
                        fora_do_horario:{" "}
                        {detalheAtual.incidente.contexto.fora_do_horario ? "sim" : "não"}
                      </span>
                      <span
                        className={`rounded px-2 py-0.5 font-medium ${
                          detalheAtual.incidente.contexto.ataque_previo_no_ativo
                            ? "bg-red-100 text-red-700"
                            : "bg-slate-200 text-slate-600"
                        }`}
                      >
                        ataque_previo:{" "}
                        {detalheAtual.incidente.contexto.ataque_previo_no_ativo ? "sim" : "não"}
                      </span>
                    </div>
                  </div>

                  {detalheAtual.decisoes.map((reg) => (
                    <div key={reg.id} className="space-y-2">
                      <div className="flex items-center justify-between text-[11px] text-slate-500">
                        <span className="font-medium">
                          Decisão {reg.decisao.prioridade} · política v
                          {reg.decisao.politica_versao}
                        </span>
                        <span>{new Date(reg.decidido_em).toLocaleTimeString("pt-BR")}</span>
                      </div>
                      <ol className="space-y-2">
                        {reg.decisao.rastro.passos.map((passo, idx) => (
                          <li key={idx} className="flex items-start gap-2.5 text-xs">
                            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-[10px] font-bold text-blue-700">
                              {idx + 1}
                            </span>
                            <div>
                              <span className="font-semibold text-slate-800">
                                {passo.etapa}:
                              </span>{" "}
                              <span className="text-slate-600">{passo.texto}</span>
                            </div>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ))}

                  {detalheAtual.eventos.length > 0 && (
                    <div className="border-t border-slate-100 pt-3">
                      <button
                        type="button"
                        onClick={() => setMostrarJson((v) => !v)}
                        className="text-xs font-semibold text-blue-600 hover:text-blue-700"
                      >
                        {mostrarJson ? "Ocultar evidências JSON" : "Ver evidências JSON"}
                      </button>
                      {mostrarJson && (
                        <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-[11px] text-slate-700">
                          {JSON.stringify(detalheAtual.eventos[0].evidencias, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* 3. Simulador de Política (Antes vs. Depois) */}
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                <Sliders className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-slate-900">
                  Simulador de Política (Antes vs. Depois)
                </h2>
                <p className="text-xs text-slate-500">
                  Recalibre criticidade de ativos e limiares sem alterar a operação em produção
                </p>
              </div>
            </div>
            <span className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
              Impacta{" "}
              <strong className="text-orange-700">
                {resultadosSimulacao.filter((r) => r.mudou).length}
              </strong>{" "}
              de {resultadosSimulacao.length} incidente(s) na fila
            </span>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
            <label className="space-y-1 text-xs">
              <span className="font-medium text-slate-600">Criticidade `servidor-pagamentos`</span>
              <select
                value={simulacao.critPagamentos}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    critPagamentos: e.target.value as Criticidade,
                  }))
                }
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-800"
              >
                <option value="alta">alta</option>
                <option value="media">media</option>
                <option value="baixa">baixa</option>
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className="font-medium text-slate-600">Criticidade `servidor-web`</span>
              <select
                value={simulacao.critWeb}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    critWeb: e.target.value as Criticidade,
                  }))
                }
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-800"
              >
                <option value="alta">alta</option>
                <option value="media">media</option>
                <option value="baixa">baixa</option>
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className="font-medium text-slate-600">
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
                className="w-full accent-blue-600"
              />
            </label>

            <label className="flex items-center gap-2 pt-5 text-xs font-medium text-slate-700">
              <input
                type="checkbox"
                checked={simulacao.sudoSempreAlto}
                onChange={(e) =>
                  setSimulacao((s) => ({ ...s, sudoSempreAlto: e.target.checked }))
                }
                className="h-4 w-4 rounded border-slate-300 accent-blue-600"
              />
              Comprometimento sempre urgência alta (pré-A5)
            </label>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {resultadosSimulacao.slice(0, 6).map(({ incidente, antes, depois, mudou }) => (
              <div
                key={incidente.id}
                className={`flex items-center justify-between rounded-lg border px-3.5 py-2.5 text-xs ${
                  mudou
                    ? "border-orange-300 bg-orange-50/70"
                    : "border-slate-200 bg-slate-50/70"
                }`}
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold text-slate-800">{incidente.categoria}</p>
                  <p className="truncate text-[11px] text-slate-500">
                    {incidente.ativo ?? "sem ativo"}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 font-bold">
                  <span
                    className={`rounded border px-1.5 py-0.5 ${ESTILO_PRIO[antes].badge}`}
                  >
                    {antes}
                  </span>
                  <span className="text-slate-400">→</span>
                  <span
                    className={`rounded border px-1.5 py-0.5 ${ESTILO_PRIO[depois].badge}`}
                  >
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
