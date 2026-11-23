import type {
  Criticidade,
  DetalheIncidente,
  Incidente,
  Prioridade,
  ResumoMetricas,
  SimulacaoDelta,
} from "./types";

export const DEMO_METRICAS_BASE: ResumoMetricas = {
  total_eventos: 2293540,
  total_incidentes: 14701,
  incidentes_por_prioridade: {
    P1: 22,
    P2: 12,
    P3: 11143,
    P4: 3524,
  },
  incidentes_por_estado: {
    aberto: 18,
    reconhecido: 16,
    resolvido: 14667,
  },
  notificacoes_por_estado: {
    enviada: 79,
    suprimida: 862,
    pendente: 0,
    falhou: 0,
  },
  taxa_reducao_eventos: 0.9936,
  tempo_medio_reconhecimento_s: 142.5,
};

export const DEMO_DETALHES: DetalheIncidente[] = [
  {
    incidente: {
      id: "8a1f3d20-1001-4b88-9001-000000000001",
      tenant_id: "demo",
      origem: "wazuh",
      categoria: "comprometimento",
      ativo: "servidor-pagamentos",
      estado: "aberto",
      prioridade: "P1",
      total_eventos: 4,
      contexto: {
        recorrencia_24h: 4,
        fora_do_horario: true,
        ataque_previo_no_ativo: true,
        confirmado: false,
      },
      aberto_em: "2026-11-23T02:14:08Z",
      atualizado_em: "2026-11-23T02:18:41Z",
      reconhecido_em: null,
      resolvido_em: null,
    },
    decisoes: [
      {
        id: "dec-001",
        tenant_id: "demo",
        evento_id: "ev-001",
        incidente_id: "8a1f3d20-1001-4b88-9001-000000000001",
        decidido_em: "2026-11-23T02:14:09Z",
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
              "comprometimento → ativo servidor-pagamentos (criticidade alta) → impacto alto → urgência alta → P1, resposta em 15 min",
            passos: [
              { etapa: "categoria", texto: "comprometimento (origem: wazuh)" },
              {
                etapa: "ativo",
                texto: "resolvido pela rede 10.0.1.0/28 → servidor-pagamentos (criticidade alta)",
              },
              { etapa: "impacto", texto: "comprometimento × criticidade alta → impacto alto" },
              {
                etapa: "urgencia",
                texto: "base média + fora_do_horario (+1) + ataque_previo_no_ativo (+1) → alta",
              },
              {
                etapa: "prioridade",
                texto: "P1, resposta em 15 min (política v4)",
              },
            ],
          },
        },
      },
    ],
    eventos: [
      {
        id: "ev-001",
        tenant_id: "demo",
        origem: "wazuh",
        id_origem: "1685715378.901",
        categoria: "comprometimento",
        severidade_origem: 10,
        ip_origem: "203.0.113.42",
        ip_destino: "10.0.1.5",
        ativo: "servidor-pagamentos",
        ocorrido_em: "2026-11-23T02:14:08Z",
        evidencias: {
          regra: { id: "5402", descricao: "Successful sudo to ROOT executed." },
        },
      },
    ],
  },
  {
    incidente: {
      id: "8a1f3d20-1001-4b88-9001-000000000002",
      tenant_id: "demo",
      origem: "suricata",
      categoria: "ataque_web",
      ativo: "servidor-web",
      estado: "reconhecido",
      prioridade: "P2",
      total_eventos: 38,
      contexto: {
        recorrencia_24h: 38,
        fora_do_horario: false,
        ataque_previo_no_ativo: false,
        confirmado: true,
      },
      aberto_em: "2026-11-23T10:05:12Z",
      atualizado_em: "2026-11-23T10:19:03Z",
      reconhecido_em: "2026-11-23T10:07:34Z",
      resolvido_em: null,
    },
    decisoes: [
      {
        id: "dec-002",
        tenant_id: "demo",
        evento_id: "ev-002",
        incidente_id: "8a1f3d20-1001-4b88-9001-000000000002",
        decidido_em: "2026-11-23T10:05:13Z",
        decisao: {
          prioridade: "P2",
          impacto: "medio",
          urgencia: "alta",
          ativo: "servidor-web",
          criticidade: "media",
          resposta: "PT1H",
          politica_versao: 4,
          prioridade_base: false,
          rastro: {
            resumo:
              "ataque_web → ativo servidor-web (criticidade média) → impacto médio → urgência alta → P2, resposta em 1 h",
            passos: [
              { etapa: "categoria", texto: "ataque_web (origem: suricata eve.json)" },
              {
                etapa: "ativo",
                texto: "resolvido pela rede 10.0.0.0/24 → servidor-web (criticidade média)",
              },
              { etapa: "impacto", texto: "ataque_web × criticidade média → impacto médio" },
              { etapa: "urgencia", texto: "base alta (sem deslocamento) → alta" },
              { etapa: "prioridade", texto: "P2, resposta em 1 h (política v4)" },
            ],
          },
        },
      },
    ],
    eventos: [
      {
        id: "ev-002",
        tenant_id: "demo",
        origem: "suricata",
        id_origem: "eve-2024364-1",
        categoria: "ataque_web",
        severidade_origem: 1,
        ip_origem: "198.51.100.19",
        ip_destino: "10.0.0.14",
        ativo: "servidor-web",
        ocorrido_em: "2026-11-23T10:05:12Z",
        evidencias: {
          suricata: {
            assinatura: "ET WEB_SERVER Possible SQL Injection Attempt",
            assinatura_id: 2024364,
            porta_destino: 443,
          },
        },
      },
    ],
  },
  {
    incidente: {
      id: "8a1f3d20-1001-4b88-9001-000000000003",
      tenant_id: "demo",
      origem: "wazuh",
      categoria: "forca_bruta",
      ativo: "servidor-web",
      estado: "aberto",
      prioridade: "P2",
      total_eventos: 64,
      contexto: {
        recorrencia_24h: 64,
        fora_do_horario: false,
        ataque_previo_no_ativo: false,
        confirmado: false,
      },
      aberto_em: "2026-11-23T11:20:00Z",
      atualizado_em: "2026-11-23T11:28:15Z",
      reconhecido_em: null,
      resolvido_em: null,
    },
    decisoes: [
      {
        id: "dec-003a",
        tenant_id: "demo",
        evento_id: "ev-003a",
        incidente_id: "8a1f3d20-1001-4b88-9001-000000000003",
        decidido_em: "2026-11-23T11:20:01Z",
        decisao: {
          prioridade: "P4",
          impacto: "baixo",
          urgencia: "media",
          ativo: "servidor-web",
          criticidade: "media",
          resposta: null,
          politica_versao: 4,
          prioridade_base: false,
          rastro: {
            passos: [
              { etapa: "categoria", texto: "forca_bruta (recorrência inicial: 1)" },
              { etapa: "prioridade", texto: "P4, sem prazo de resposta (política v4)" },
            ],
          },
        },
      },
      {
        id: "dec-003b",
        tenant_id: "demo",
        evento_id: "ev-003b",
        incidente_id: "8a1f3d20-1001-4b88-9001-000000000003",
        decidido_em: "2026-11-23T11:27:40Z",
        decisao: {
          prioridade: "P3",
          impacto: "baixo",
          urgencia: "alta",
          ativo: "servidor-web",
          criticidade: "media",
          resposta: "PT24H",
          politica_versao: 4,
          prioridade_base: false,
          rastro: {
            passos: [
              { etapa: "categoria", texto: "forca_bruta (origem: wazuh)" },
              { etapa: "ativo", texto: "servidor-web (criticidade média)" },
              { etapa: "urgencia", texto: "modificador recorrencia_24h >= 50 (+1) → alta" },
              { etapa: "prioridade", texto: "P3, resposta em 24 h (ADR 0003: decisão gravada na subida)" },
            ],
          },
        },
      },
    ],
    eventos: [
      {
        id: "ev-003b",
        tenant_id: "demo",
        origem: "wazuh",
        id_origem: "1685715378.5716",
        categoria: "forca_bruta",
        severidade_origem: 5,
        ip_origem: "203.0.113.7",
        ip_destino: "10.0.0.14",
        ativo: "servidor-web",
        ocorrido_em: "2026-11-23T11:27:40Z",
        evidencias: {
          regra: { id: "5716", descricao: "sshd: authentication failed." },
        },
      },
    ],
  },
  {
    incidente: {
      id: "8a1f3d20-1001-4b88-9001-000000000004",
      tenant_id: "demo",
      origem: "suricata",
      categoria: "reconhecimento",
      ativo: "ambiente-testes",
      estado: "aberto",
      prioridade: "P3",
      total_eventos: 192,
      contexto: {
        recorrencia_24h: 192,
        fora_do_horario: false,
        ataque_previo_no_ativo: false,
        confirmado: false,
      },
      aberto_em: "2026-11-23T12:10:00Z",
      atualizado_em: "2026-11-23T12:14:22Z",
      reconhecido_em: null,
      resolvido_em: null,
    },
    decisoes: [
      {
        id: "dec-004",
        tenant_id: "demo",
        evento_id: "ev-004",
        incidente_id: "8a1f3d20-1001-4b88-9001-000000000004",
        decidido_em: "2026-11-23T12:10:15Z",
        decisao: {
          prioridade: "P3",
          impacto: "baixo",
          urgencia: "alta",
          ativo: "ambiente-testes",
          criticidade: "baixa",
          resposta: "PT24H",
          politica_versao: 4,
          prioridade_base: false,
          rastro: {
            passos: [
              { etapa: "categoria", texto: "reconhecimento (origem: suricata)" },
              {
                etapa: "ativo",
                texto: "rede 10.0.9.0/24 → ambiente-testes (criticidade baixa)",
              },
              { etapa: "impacto", texto: "reconhecimento × criticidade baixa → impacto baixo" },
              {
                etapa: "urgencia",
                texto: "base baixa + recorrencia_24h >= 5 (+1) → média; teto P3",
              },
              { etapa: "prioridade", texto: "P3, entra apenas no resumo diário (08:00)" },
            ],
          },
        },
      },
    ],
    eventos: [
      {
        id: "ev-004",
        tenant_id: "demo",
        origem: "suricata",
        id_origem: "eve-scan-01",
        categoria: "reconhecimento",
        severidade_origem: 2,
        ip_origem: "198.51.100.77",
        ip_destino: "10.0.9.20",
        ativo: "ambiente-testes",
        ocorrido_em: "2026-11-23T12:10:00Z",
        evidencias: {
          suricata: {
            assinatura: "ET SCAN Possible Nmap User-Agent Observed",
            assinatura_id: 2024364,
            porta_destino: 80,
          },
        },
      },
    ],
  },
  {
    incidente: {
      id: "8a1f3d20-1001-4b88-9001-000000000005",
      tenant_id: "demo",
      origem: "wazuh",
      categoria: "benigno",
      ativo: "servidor-web",
      estado: "resolvido",
      prioridade: "P4",
      total_eventos: 410,
      contexto: {
        recorrencia_24h: 410,
        fora_do_horario: false,
        ataque_previo_no_ativo: false,
        confirmado: false,
      },
      aberto_em: "2026-11-23T09:00:00Z",
      atualizado_em: "2026-11-23T09:28:11Z",
      reconhecido_em: null,
      resolvido_em: "2026-11-23T09:58:11Z",
    },
    decisoes: [
      {
        id: "dec-005",
        tenant_id: "demo",
        evento_id: "ev-005",
        incidente_id: "8a1f3d20-1001-4b88-9001-000000000005",
        decidido_em: "2026-11-23T09:00:01Z",
        decisao: {
          prioridade: "P4",
          impacto: "baixo",
          urgencia: "media",
          ativo: "servidor-web",
          criticidade: "media",
          resposta: null,
          politica_versao: 4,
          prioridade_base: false,
          rastro: {
            passos: [
              { etapa: "categoria", texto: "benigno (PAM session opened/closed)" },
              { etapa: "prioridade", texto: "P4, modo nunca → visível apenas no dashboard" },
            ],
          },
        },
      },
    ],
    eventos: [
      {
        id: "ev-005",
        tenant_id: "demo",
        origem: "wazuh",
        id_origem: "1685715378.5501",
        categoria: "benigno",
        severidade_origem: 3,
        ip_origem: null,
        ip_destino: "10.0.0.14",
        ativo: "servidor-web",
        ocorrido_em: "2026-11-23T09:00:00Z",
        evidencias: {
          regra: { id: "5501", descricao: "PAM: Login session opened." },
        },
      },
    ],
  },
];

export function simularPrioridadeLocal(
  inc: Incidente,
  delta: SimulacaoDelta
): { antes: Prioridade; depois: Prioridade } {
  const antes = inc.prioridade ?? "P3";
  let crit: Criticidade = "media";
  if (inc.ativo === "servidor-pagamentos") crit = delta.critPagamentos;
  else if (inc.ativo === "servidor-web") crit = delta.critWeb;
  else if (inc.ativo === "ambiente-testes") crit = "baixa";

  let impacto: "alto" | "medio" | "baixo" = "baixo";
  if (inc.categoria === "comprometimento" || inc.categoria === "exfiltracao") {
    impacto = crit === "baixa" ? "medio" : "alto";
  } else if (inc.categoria === "ataque_web" || inc.categoria === "negacao_servico") {
    impacto = crit === "alta" ? "alto" : crit === "media" ? "medio" : "baixo";
  } else if (inc.categoria === "forca_bruta") {
    impacto = crit === "alta" ? "medio" : "baixo";
  }

  let urgencia: "alta" | "media" | "baixa" = "baixa";
  if (inc.categoria === "ataque_web" || inc.categoria === "negacao_servico") {
    urgencia = "alta";
  } else if (inc.categoria === "comprometimento") {
    urgencia =
      delta.sudoSempreAlto || inc.contexto.fora_do_horario || inc.contexto.ataque_previo_no_ativo
        ? "alta"
        : "media";
  } else if (inc.categoria === "forca_bruta") {
    urgencia = inc.contexto.recorrencia_24h >= delta.limiarForcaBruta ? "alta" : "media";
  } else if (inc.categoria === "reconhecimento") {
    urgencia = inc.contexto.recorrencia_24h >= 5 ? "media" : "baixa";
  }

  const matriz: Record<string, Record<string, Prioridade>> = {
    alto: { alta: "P1", media: "P2", baixa: "P3" },
    medio: { alta: "P2", media: "P3", baixa: "P4" },
    baixo: { alta: "P3", media: "P4", baixa: "P4" },
  };
  return { antes, depois: matriz[impacto][urgencia] };
}
