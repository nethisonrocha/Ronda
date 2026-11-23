"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  Bell,
  CheckCircle2,
  GitBranch,
  Moon,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Sliders,
  Sun,
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
  escuro = false,
}: {
  titulo: string;
  centroValor: string;
  centroSub: string;
  fatias: FatiaRosca[];
  escuro?: boolean;
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
      <p className={`mb-4 text-xs font-semibold ${escuro ? "text-slate-200" : "text-slate-700"}`}>
        {titulo}
      </p>
      <div className="flex items-center gap-5">
        <div className="relative h-40 w-40 shrink-0">
          <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
            <circle
              cx="50"
              cy="50"
              r={raio}
              fill="transparent"
              stroke={escuro ? "#1E293B" : "#E2E8F0"}
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
            <span
              className={`text-lg font-bold tabular-nums ${
                escuro ? "text-white" : "text-slate-900"
              }`}
            >
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
                <span
                  className={`flex items-center gap-1.5 ${
                    escuro ? "text-slate-300" : "text-slate-600"
                  }`}
                >
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: f.cor }}
                  />
                  {f.rotulo}
                </span>
                <span
                  className={`font-semibold tabular-nums ${
                    escuro ? "text-slate-100" : "text-slate-800"
                  }`}
                >
                  {pct}%
                </span>
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
  const [celulaMatriz, setCelulaMatriz] = useState<{
    impacto: string;
    urgencia: string;
    prioridade: Prioridade;
  } | null>(null);
  const [temaEscuro, setTemaEscuro] = useState(false);
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
    for (const inc of listaIncidentes) {
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
  }, [listaIncidentes]);

  const fatiasPrioridade: FatiaRosca[] = useMemo(() => {
    const todas: FatiaRosca[] = [
      { rotulo: "P1 Crítico", valor: metricas.incidentes_por_prioridade.P1 ?? 0, cor: "#DC2626" },
      { rotulo: "P2 Alto", valor: metricas.incidentes_por_prioridade.P2 ?? 0, cor: "#EA580C" },
      { rotulo: "P3 Médio", valor: metricas.incidentes_por_prioridade.P3 ?? 0, cor: "#EAB308" },
      { rotulo: "P4 Baixo", valor: metricas.incidentes_por_prioridade.P4 ?? 0, cor: "#16A34A" },
    ];
    if (filtroPrioridade === "TODAS") return todas;
    return todas.map((f) =>
      f.rotulo.startsWith(filtroPrioridade) ? f : { ...f, valor: 0 }
    );
  }, [metricas, filtroPrioridade]);

  const totalPrioridadeFiltrada = useMemo(
    () => fatiasPrioridade.reduce((acc, f) => acc + f.valor, 0),
    [fatiasPrioridade]
  );

  const fatiasOrigem: FatiaRosca[] = useMemo(() => {
    const porCat = new Map<string, number>();
    for (const inc of listaIncidentes) {
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
  }, [listaIncidentes]);

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

  function selecionarPrioridade(prio: "TODAS" | Prioridade) {
    setFiltroPrioridade(prio);
    setCelulaMatriz(null);
    if (modo === "api" && token.trim()) {
      void carregarDaApi(apiUrl, token, prio);
    }
  }

  function clicarCelulaMatriz(impacto: string, urgencia: string, prioridade: Prioridade) {
    const mesma =
      celulaMatriz?.impacto === impacto && celulaMatriz?.urgencia === urgencia;
    if (mesma) {
      selecionarPrioridade("TODAS");
      return;
    }
    setCelulaMatriz({ impacto, urgencia, prioridade });
    setFiltroPrioridade(prioridade);
    if (modo === "api" && token.trim()) {
      void carregarDaApi(apiUrl, token, prioridade);
    }
  }

  const escuro = temaEscuro;
  const cardCls = escuro
    ? "rounded-xl border border-slate-800 bg-[#111827] shadow-sm"
    : "rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.03)]";
  const txtTitulo = escuro ? "text-slate-100" : "text-slate-900";
  const txtSub = escuro ? "text-slate-400" : "text-slate-500";
  const bordaDiv = escuro ? "border-slate-800" : "border-slate-200";
  const bordaSuave = escuro ? "border-slate-800/80" : "border-slate-100";
  const inputCls = escuro
    ? "rounded-lg border border-slate-700 bg-slate-900 text-slate-100 focus:border-blue-500 focus:outline-none"
    : "rounded-lg border border-slate-200 bg-white text-slate-800 focus:border-blue-500 focus:outline-none";

  const celulasMatriz: {
    impacto: string;
    urgencia: string;
    prioridade: Prioridade;
    cor: string;
    qtd?: number;
  }[] = [
    { impacto: "Alto", urgencia: "Baixa", prioridade: "P3", cor: "bg-amber-400 text-slate-950" },
    { impacto: "Alto", urgencia: "Média", prioridade: "P2", cor: "bg-orange-500 text-white", qtd: qtdP2 },
    { impacto: "Alto", urgencia: "Alta", prioridade: "P1", cor: "bg-red-600 text-white shadow-sm", qtd: qtdP1 },
    { impacto: "Médio", urgencia: "Baixa", prioridade: "P4", cor: "bg-emerald-500 text-white" },
    { impacto: "Médio", urgencia: "Média", prioridade: "P3", cor: "bg-amber-400 text-slate-950", qtd: qtdP3 },
    { impacto: "Médio", urgencia: "Alta", prioridade: "P2", cor: "bg-orange-500 text-white" },
    { impacto: "Baixo", urgencia: "Baixa", prioridade: "P4", cor: "bg-emerald-600 text-white", qtd: qtdP4 },
    { impacto: "Baixo", urgencia: "Média", prioridade: "P4", cor: "bg-emerald-500 text-white" },
    { impacto: "Baixo", urgencia: "Alta", prioridade: "P3", cor: "bg-amber-400 text-slate-950" },
  ];

  return (
    <div
      className={`min-h-screen transition-colors ${
        escuro ? "bg-[#0B1120] text-slate-100" : "bg-[#F8FAFC] text-[#0F172A]"
      }`}
    >
      {/* Header corporativo limpo */}
      <header className={`border-b ${bordaDiv} ${escuro ? "bg-[#111827]" : "bg-white"}`}>
        <div className="flex w-full flex-wrap items-center justify-between gap-4 px-6 py-3.5">
          <h1 className={`text-xl font-bold tracking-tight ${txtTitulo}`}>Ronda</h1>

          <div className="flex flex-wrap items-center gap-2.5">
            <div
              className={`flex rounded-lg border p-0.5 text-xs ${
                escuro ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-slate-100"
              }`}
            >
              <button
                type="button"
                onClick={() => {
                  setModo("demo");
                  setErroApi(null);
                }}
                className={`rounded-md px-3 py-1.5 font-medium transition ${
                  modo === "demo"
                    ? escuro
                      ? "bg-slate-800 text-white shadow-sm"
                      : "bg-white text-slate-900 shadow-sm"
                    : escuro
                      ? "text-slate-400 hover:text-white"
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
                    ? escuro
                      ? "bg-slate-800 text-emerald-400 shadow-sm"
                      : "bg-white text-emerald-700 shadow-sm"
                    : escuro
                      ? "text-slate-400 hover:text-white"
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
                  className={`w-44 px-2.5 py-1.5 text-xs ${inputCls}`}
                />
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Token rnd_..."
                  className={`w-40 px-2.5 py-1.5 text-xs ${inputCls}`}
                />
                <button
                  type="button"
                  onClick={() => void carregarDaApi()}
                  disabled={carregando}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
                    escuro
                      ? "border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
                      : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${carregando ? "animate-spin" : ""}`} />
                  Conectar
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => setTemaEscuro((v) => !v)}
              title={escuro ? "Mudar para modo claro" : "Mudar para modo escuro"}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                escuro
                  ? "border-slate-700 bg-slate-800 text-amber-300 hover:bg-slate-700"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {escuro ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
              {escuro ? "Claro" : "Escuro"}
            </button>

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

      <main className="w-full space-y-5 px-6 py-5">
        {erroApi && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-medium text-red-700">
            {erroApi}
          </div>
        )}

        {/* 1. Linha de 4 Cards KPI (estilo corporativo com ícone pastel à esquerda) */}
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className={`flex items-center gap-4 p-4 ${cardCls}`}>
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                escuro ? "bg-blue-500/15 text-blue-400" : "bg-blue-50 text-blue-600"
              }`}
            >
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <p className={`text-xs font-medium ${txtSub}`}>Eventos Ingeridos</p>
              <p className={`mt-0.5 text-2xl font-bold tabular-nums ${txtTitulo}`}>
                {FORMATO_NUM.format(metricas.total_eventos)}
              </p>
              <p className={`mt-0.5 text-xs ${txtSub}`}>Wazuh + Suricata eve.json</p>
            </div>
          </div>

          <div className={`flex items-center gap-4 p-4 ${cardCls}`}>
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                escuro ? "bg-orange-500/15 text-orange-400" : "bg-orange-50 text-orange-600"
              }`}
            >
              <GitBranch className="h-5 w-5" />
            </div>
            <div>
              <p className={`text-xs font-medium ${txtSub}`}>Incidentes Correlacionados</p>
              <p className={`mt-0.5 text-2xl font-bold tabular-nums ${txtTitulo}`}>
                {FORMATO_NUM.format(metricas.total_incidentes)}
              </p>
              <p
                className={`mt-0.5 text-xs font-medium ${
                  escuro ? "text-emerald-400" : "text-emerald-700"
                }`}
              >
                Redução de {(metricas.taxa_reducao_eventos * 100).toFixed(2)}%
              </p>
            </div>
          </div>

          <div className={`flex items-center gap-4 p-4 ${cardCls}`}>
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                escuro ? "bg-purple-500/15 text-purple-400" : "bg-purple-50 text-purple-600"
              }`}
            >
              <Bell className="h-5 w-5" />
            </div>
            <div>
              <p className={`text-xs font-medium ${txtSub}`}>Notificações Enviadas</p>
              <p className={`mt-0.5 text-2xl font-bold tabular-nums ${txtTitulo}`}>
                {FORMATO_NUM.format(metricas.notificacoes_por_estado.enviada ?? 0)}
              </p>
              <p className={`mt-0.5 text-xs ${txtSub}`}>
                {FORMATO_NUM.format(metricas.notificacoes_por_estado.suprimida ?? 0)} suprimidas
                anti-fadiga
              </p>
            </div>
          </div>

          <div
            className={`flex items-center gap-4 p-4 ${cardCls} ${
              qtdP1 > 0
                ? escuro
                  ? "!border-red-500/40"
                  : "!border-red-200"
                : escuro
                  ? "!border-emerald-500/40"
                  : "!border-emerald-200"
            }`}
          >
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${
                qtdP1 > 0
                  ? escuro
                    ? "bg-red-500/15 text-red-400"
                    : "bg-red-50 text-red-600"
                  : escuro
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "bg-emerald-50 text-emerald-600"
              }`}
            >
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <p className={`text-xs font-medium ${txtSub}`}>Nível de Ação Atual</p>
              <p
                className={`mt-0.5 text-2xl font-bold ${
                  qtdP1 > 0
                    ? escuro
                      ? "text-red-400"
                      : "text-red-600"
                    : escuro
                      ? "text-emerald-400"
                      : "text-emerald-700"
                }`}
              >
                {qtdP1 > 0 ? "P1 Crítico" : "Normal"}
              </p>
              <p className={`mt-0.5 text-xs font-medium ${txtSub}`}>
                {FORMATO_NUM.format(qtdP1)} P1 · {FORMATO_NUM.format(qtdP2)} P2 em acompanhamento
              </p>
            </div>
          </div>
        </section>

        {/* 2. Grade Principal (2 linhas x 3 colunas alinhadas no topo e na base) */}
        <section className="grid grid-cols-1 items-stretch gap-5 lg:grid-cols-12">
          {/* Linha 1 - Col 1 (3/12): Matriz de Calor ITIL 3x3 clicável */}
          <div
            className={`flex h-full flex-col justify-between p-5 lg:col-span-3 lg:col-start-1 lg:row-start-1 ${cardCls}`}
          >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className={`text-sm font-bold ${txtTitulo}`}>Matriz de Calor ITIL</h2>
                  <p className={`mt-0.5 text-xs ${txtSub}`}>
                    Clique em uma célula para filtrar a fila
                  </p>
                </div>
                {celulaMatriz && (
                  <button
                    type="button"
                    onClick={() => selecionarPrioridade("TODAS")}
                    className="rounded-md bg-blue-600/10 px-2 py-1 text-[11px] font-semibold text-blue-600 hover:bg-blue-600/20"
                  >
                    Limpar
                  </button>
                )}
              </div>

              <div className="mt-4">
                <div className="grid grid-cols-4 gap-1.5 text-center text-[11px]">
                  <div />
                  <div className={`font-semibold ${txtSub}`}>Baixa</div>
                  <div className={`font-semibold ${txtSub}`}>Média</div>
                  <div className={`font-semibold ${txtSub}`}>Alta</div>

                  {(["Alto", "Médio", "Baixo"] as const).map((imp) => (
                    <div key={imp} className="contents">
                      <div className={`flex items-center justify-end pr-1.5 font-semibold ${txtSub}`}>
                        {imp}
                      </div>
                      {celulasMatriz
                        .filter((c) => c.impacto === imp)
                        .map((c) => {
                          const ativa =
                            celulaMatriz?.impacto === c.impacto &&
                            celulaMatriz?.urgencia === c.urgencia;
                          return (
                            <button
                              key={`${c.impacto}-${c.urgencia}`}
                              type="button"
                              onClick={() => clicarCelulaMatriz(c.impacto, c.urgencia, c.prioridade)}
                              title={`Filtrar ${c.prioridade} (${c.impacto} × ${c.urgencia})`}
                              className={`cursor-pointer rounded-md px-1 py-2.5 font-bold transition hover:scale-[1.03] ${c.cor} ${
                                ativa
                                  ? escuro
                                    ? "ring-2 ring-white ring-offset-2 ring-offset-[#111827]"
                                    : "ring-2 ring-slate-900 ring-offset-2 ring-offset-white"
                                  : "opacity-95 hover:opacity-100"
                              }`}
                            >
                              <div className="text-[10px] font-semibold">{c.prioridade}</div>
                              {c.qtd !== undefined && (
                                <div className="tabular-nums">{FORMATO_NUM.format(c.qtd)}</div>
                              )}
                            </button>
                          );
                        })}
                    </div>
                  ))}
                </div>
                <p className={`mt-2.5 text-center text-[11px] font-medium ${txtSub}`}>
                  {celulaMatriz
                    ? `Filtro ativo: ${celulaMatriz.impacto} × ${celulaMatriz.urgencia} (${celulaMatriz.prioridade})`
                    : "Eixo Horizontal: Urgência · Eixo Vertical: Impacto"}
                </p>
              </div>
            </div>

            {/* Linha 2 - Col 1 (3/12): Legenda Nível de Prioridade */}
            <div
              className={`flex h-full flex-col p-5 lg:col-span-3 lg:col-start-1 lg:row-start-2 ${cardCls}`}
            >
              <h3 className={`text-xs font-bold uppercase tracking-wide ${txtTitulo}`}>
                Níveis de Prioridade (SLA)
              </h3>
              <ul className="mt-3 space-y-2.5 text-xs">
                <li className="flex items-center justify-between">
                  <span className={`flex items-center gap-2 font-medium ${txtSub}`}>
                    <span className="h-2.5 w-2.5 rounded-full bg-red-600" />
                    P1 Crítico (Imediato · 15 min)
                  </span>
                  <span
                    className={`font-bold tabular-nums ${
                      escuro ? "text-red-400" : "text-red-700"
                    }`}
                  >
                    {FORMATO_NUM.format(qtdP1)}
                  </span>
                </li>
                <li className="flex items-center justify-between">
                  <span className={`flex items-center gap-2 font-medium ${txtSub}`}>
                    <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
                    P2 Alto (Agrupado · 1 h)
                  </span>
                  <span
                    className={`font-bold tabular-nums ${
                      escuro ? "text-orange-400" : "text-orange-700"
                    }`}
                  >
                    {FORMATO_NUM.format(qtdP2)}
                  </span>
                </li>
                <li className="flex items-center justify-between">
                  <span className={`flex items-center gap-2 font-medium ${txtSub}`}>
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                    P3 Médio (Resumo diário · 24 h)
                  </span>
                  <span
                    className={`font-bold tabular-nums ${
                      escuro ? "text-amber-400" : "text-amber-700"
                    }`}
                  >
                    {FORMATO_NUM.format(qtdP3)}
                  </span>
                </li>
                <li className="flex items-center justify-between">
                  <span className={`flex items-center gap-2 font-medium ${txtSub}`}>
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
                    P4 Baixo (Apenas painel)
                  </span>
                  <span
                    className={`font-bold tabular-nums ${
                      escuro ? "text-emerald-400" : "text-emerald-700"
                    }`}
                  >
                    {FORMATO_NUM.format(qtdP4)}
                  </span>
                </li>
              </ul>
            </div>

          {/* Linha 1 - Col 2 (6/12): Distribuição dos Incidentes */}
            <div
              className={`flex h-full flex-col justify-between p-5 lg:col-span-6 lg:col-start-4 lg:row-start-1 ${cardCls}`}
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className={`text-sm font-bold ${txtTitulo}`}>
                  Distribuição dos Incidentes
                </h2>
                <span
                  className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                    escuro ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {filtroPrioridade === "TODAS"
                    ? `Base: ${FORMATO_NUM.format(metricas.total_incidentes)}`
                    : `Filtro ${filtroPrioridade}: ${FORMATO_NUM.format(totalPrioridadeFiltrada)}`}
                </span>
              </div>
              <div className="my-auto grid grid-cols-1 gap-6 sm:grid-cols-2">
                <GraficoRosca
                  titulo="Por Prioridade ITIL"
                  centroValor={FORMATO_NUM.format(totalPrioridadeFiltrada)}
                  centroSub={filtroPrioridade === "TODAS" ? "TOTAL" : filtroPrioridade}
                  fatias={fatiasPrioridade}
                  escuro={escuro}
                />
                <GraficoRosca
                  titulo="Por Categoria na Fila"
                  centroValor={String(listaIncidentes.length)}
                  centroSub="FILA"
                  fatias={fatiasOrigem}
                  escuro={escuro}
                />
              </div>
            </div>

            <div
              className={`flex h-full flex-col p-5 lg:col-span-6 lg:col-start-4 lg:row-start-2 ${cardCls}`}
            >
              <div className="flex items-center justify-between">
                <h2 className={`text-sm font-bold ${txtTitulo}`}>Rastro da Decisão ITIL</h2>
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
                <p className={`mt-4 text-xs ${txtSub}`}>
                  Selecione um incidente na fila para inspecionar o rastro determinístico.
                </p>
              ) : (
                <div className="mt-4 space-y-4">
                  <div
                    className={`rounded-lg border p-3 text-xs ${
                      escuro
                        ? "border-slate-800 bg-slate-900/70"
                        : "border-slate-200 bg-slate-50"
                    }`}
                  >
                    <p className={`font-semibold ${txtTitulo}`}>
                      {detalheAtual.incidente.categoria} em{" "}
                      {detalheAtual.incidente.ativo ?? "ativo desconhecido"}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                      <span
                        className={`rounded px-2 py-0.5 font-medium ${
                          detalheAtual.incidente.contexto.fora_do_horario
                            ? "bg-amber-100 text-amber-800"
                            : escuro
                              ? "bg-slate-800 text-slate-300"
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
                            : escuro
                              ? "bg-slate-800 text-slate-300"
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
                      <div className={`flex items-center justify-between text-[11px] ${txtSub}`}>
                        <span className="font-medium">
                          Decisão {reg.decisao.prioridade} · política v
                          {reg.decisao.politica_versao}
                        </span>
                        <span>{new Date(reg.decidido_em).toLocaleTimeString("pt-BR")}</span>
                      </div>
                      <ol className="space-y-2">
                        {reg.decisao.rastro.passos.map((passo, idx) => (
                          <li key={idx} className="flex items-start gap-2.5 text-xs">
                            <span
                              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                                escuro
                                  ? "bg-blue-500/20 text-blue-300"
                                  : "bg-blue-50 text-blue-700"
                              }`}
                            >
                              {idx + 1}
                            </span>
                            <div>
                              <span className={`font-semibold ${txtTitulo}`}>
                                {passo.etapa}:
                              </span>{" "}
                              <span className={txtSub}>{passo.texto}</span>
                            </div>
                          </li>
                        ))}
                      </ol>
                    </div>
                  ))}

                  {detalheAtual.eventos.length > 0 && (
                    <div className={`border-t pt-3 ${bordaSuave}`}>
                      <button
                        type="button"
                        onClick={() => setMostrarJson((v) => !v)}
                        className="text-xs font-semibold text-blue-600 hover:text-blue-500"
                      >
                        {mostrarJson ? "Ocultar evidências JSON" : "Ver evidências JSON"}
                      </button>
                      {mostrarJson && (
                        <pre
                          className={`mt-2 max-h-40 overflow-auto rounded-lg border p-2.5 text-[11px] ${
                            escuro
                              ? "border-slate-800 bg-slate-950 text-slate-300"
                              : "border-slate-200 bg-slate-50 text-slate-700"
                          }`}
                        >
                          {JSON.stringify(detalheAtual.eventos[0].evidencias, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

          {/* Linha 1 - Col 3 (3/12): Principais Ativos Afetados */}
            <div
              className={`flex h-full flex-col p-5 lg:col-span-3 lg:col-start-10 lg:row-start-1 ${cardCls}`}
            >
              <div className="flex items-center justify-between">
                <h2 className={`text-sm font-bold ${txtTitulo}`}>
                  Principais Ativos Afetados
                </h2>
                <span className={`text-xs font-medium ${txtSub}`}>Eventos</span>
              </div>
              <ul
                className={`mt-3 divide-y text-xs ${
                  escuro ? "divide-slate-800" : "divide-slate-100"
                }`}
              >
                {topAtivos.length === 0 ? (
                  <li className={`py-4 ${txtSub}`}>Sem ativos registrados.</li>
                ) : (
                  topAtivos.map((item) => (
                    <li
                      key={item.ativo}
                      className="flex items-center justify-between py-2.5"
                    >
                      <span className={`flex items-center gap-2 font-medium ${txtSub}`}>
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${ESTILO_PRIO[item.prio].ponto}`}
                        />
                        {item.ativo}
                      </span>
                      <span className={`font-bold tabular-nums ${txtTitulo}`}>
                        {FORMATO_NUM.format(item.eventos)}
                      </span>
                    </li>
                  ))
                )}
              </ul>
            </div>

            <div
              className={`flex h-full flex-col lg:col-span-3 lg:col-start-10 lg:row-start-2 ${cardCls}`}
            >
              <div className={`space-y-2.5 border-b px-4 py-3.5 ${bordaDiv}`}>
                <h2 className={`text-sm font-bold ${txtTitulo}`}>
                  Fila de Incidentes ({listaIncidentes.length})
                </h2>
                <div className="flex flex-wrap items-center gap-1">
                  {(["TODAS", "P1", "P2", "P3", "P4"] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => selecionarPrioridade(p)}
                      className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                        filtroPrioridade === p
                          ? "bg-blue-600 text-white"
                          : escuro
                            ? "bg-slate-800 text-slate-300 hover:bg-slate-700"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div className={`border-b px-4 py-2.5 ${bordaSuave}`}>
                <div className="relative">
                  <Search className="pointer-events-none absolute top-2 left-2.5 h-3.5 w-3.5 text-slate-400" />
                  <input
                    value={busca}
                    onChange={(e) => setBusca(e.target.value)}
                    placeholder="Filtrar ativo ou categoria..."
                    className={`w-full py-1.5 pr-3 pl-8 text-xs ${
                      escuro
                        ? "rounded-lg border border-slate-700 bg-slate-900 text-slate-100 focus:border-blue-500 focus:outline-none"
                        : "rounded-lg border border-slate-200 bg-slate-50 text-slate-800 focus:border-blue-500 focus:bg-white focus:outline-none"
                    }`}
                  />
                </div>
              </div>

              <div className={`max-h-[420px] flex-1 divide-y overflow-y-auto ${escuro ? "divide-slate-800" : "divide-slate-100"}`}>
                {listaIncidentes.length === 0 ? (
                  <div className={`px-4 py-8 text-center text-xs ${txtSub}`}>
                    Nenhum incidente encontrado.
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
                        className={`cursor-pointer space-y-2 px-4 py-3 transition ${
                          selecionado
                            ? escuro
                              ? "bg-blue-500/10"
                              : "bg-blue-50/70"
                            : escuro
                              ? "hover:bg-slate-800/50"
                              : "hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-1.5">
                            <span
                              className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${estilo.badge}`}
                            >
                              <span className={`h-1.5 w-1.5 rounded-full ${estilo.ponto}`} />
                              {prio}
                            </span>
                            <span className={`truncate text-xs font-semibold ${txtTitulo}`}>
                              {inc.categoria}
                            </span>
                          </div>
                          <span
                            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                              inc.origem === "suricata"
                                ? "bg-orange-50 text-orange-700"
                                : "bg-blue-50 text-blue-700"
                            }`}
                          >
                            {inc.origem}
                          </span>
                        </div>

                        <div className="flex items-center justify-between gap-2">
                          <p className={`truncate text-[11px] ${txtSub}`}>
                            <span className={`font-medium ${txtTitulo}`}>
                              {inc.ativo ?? "sem ativo"}
                            </span>{" "}
                            · {inc.total_eventos} ev.
                          </p>
                          {inc.estado === "aberto" ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                void reconhecer(inc.id);
                              }}
                              className="shrink-0 rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-semibold text-blue-700 hover:bg-blue-100"
                            >
                              Reconhecer
                            </button>
                          ) : (
                            <span
                              className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium ${
                                escuro
                                  ? "border-slate-700 bg-slate-800 text-slate-300"
                                  : "border-slate-200 bg-slate-100 text-slate-600"
                              }`}
                            >
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
        </section>

        {/* 3. Simulador de Política (Antes vs. Depois) */}
        <section className={`p-5 ${cardCls}`}>
          <div
            className={`flex flex-wrap items-center justify-between gap-2 border-b pb-4 ${bordaSuave}`}
          >
            <div className="flex items-center gap-2.5">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                  escuro ? "bg-blue-500/20 text-blue-400" : "bg-blue-50 text-blue-600"
                }`}
              >
                <Sliders className="h-4 w-4" />
              </div>
              <div>
                <h2 className={`text-sm font-bold ${txtTitulo}`}>
                  Simulador de Política (Antes vs. Depois)
                </h2>
                <p className={`text-xs ${txtSub}`}>
                  Recalibre criticidade de ativos e limiares sem alterar a operação em produção
                </p>
              </div>
            </div>
            <span
              className={`rounded-lg px-3 py-1 text-xs font-medium ${
                escuro ? "bg-slate-800 text-slate-200" : "bg-slate-100 text-slate-700"
              }`}
            >
              Impacta{" "}
              <strong className={escuro ? "text-orange-400" : "text-orange-700"}>
                {resultadosSimulacao.filter((r) => r.mudou).length}
              </strong>{" "}
              de {resultadosSimulacao.length} incidente(s) na fila
            </span>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
            <label className="space-y-1 text-xs">
              <span className={`font-medium ${txtSub}`}>Criticidade `servidor-pagamentos`</span>
              <select
                value={simulacao.critPagamentos}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    critPagamentos: e.target.value as Criticidade,
                  }))
                }
                className={`w-full px-3 py-2 text-xs font-medium ${inputCls}`}
              >
                <option value="alta">alta</option>
                <option value="media">media</option>
                <option value="baixa">baixa</option>
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className={`font-medium ${txtSub}`}>Criticidade `servidor-web`</span>
              <select
                value={simulacao.critWeb}
                onChange={(e) =>
                  setSimulacao((s) => ({
                    ...s,
                    critWeb: e.target.value as Criticidade,
                  }))
                }
                className={`w-full px-3 py-2 text-xs font-medium ${inputCls}`}
              >
                <option value="alta">alta</option>
                <option value="media">media</option>
                <option value="baixa">baixa</option>
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className={`font-medium ${txtSub}`}>
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

            <label className={`flex items-center gap-2 pt-5 text-xs font-medium ${txtSub}`}>
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
                    ? escuro
                      ? "border-orange-500/40 bg-orange-500/10"
                      : "border-orange-300 bg-orange-50/70"
                    : escuro
                      ? "border-slate-800 bg-slate-900/50"
                      : "border-slate-200 bg-slate-50/70"
                }`}
              >
                <div className="min-w-0">
                  <p className={`truncate font-semibold ${txtTitulo}`}>{incidente.categoria}</p>
                  <p className={`truncate text-[11px] ${txtSub}`}>
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
