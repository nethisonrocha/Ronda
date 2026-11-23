export type Prioridade = "P1" | "P2" | "P3" | "P4";
export type EstadoIncidente = "aberto" | "reconhecido" | "resolvido";
export type Criticidade = "baixa" | "media" | "alta";

export interface ContextoIncidente {
  recorrencia_24h: number;
  fora_do_horario: boolean;
  ataque_previo_no_ativo: boolean;
  confirmado: boolean;
}

export interface Incidente {
  id: string;
  tenant_id: string;
  origem: string;
  categoria: string;
  ativo: string | null;
  estado: EstadoIncidente;
  prioridade: Prioridade | null;
  total_eventos: number;
  contexto: ContextoIncidente;
  aberto_em: string;
  atualizado_em: string;
  reconhecido_em: string | null;
  resolvido_em: string | null;
}

export interface PassoRastro {
  etapa: string;
  texto: string;
  dados?: Record<string, unknown>;
}

export interface Rastro {
  passos: PassoRastro[];
  resumo?: string;
}

export interface Decisao {
  prioridade: Prioridade;
  impacto: string | null;
  urgencia: string | null;
  ativo: string | null;
  criticidade: Criticidade;
  resposta: string | null;
  politica_versao: number;
  prioridade_base: boolean;
  rastro: Rastro;
}

export interface DecisaoRegistrada {
  id: string;
  tenant_id: string;
  evento_id: string | null;
  incidente_id: string | null;
  decidido_em: string;
  decisao: Decisao;
}

export interface Evento {
  id: string;
  tenant_id: string;
  origem: string;
  id_origem: string | null;
  categoria: string;
  severidade_origem: number | string | null;
  ip_origem: string | null;
  ip_destino: string | null;
  ativo: string | null;
  ocorrido_em: string;
  evidencias: Record<string, unknown>;
}

export interface DetalheIncidente {
  incidente: Incidente;
  decisoes: DecisaoRegistrada[];
  eventos: Evento[];
}

export interface ResumoMetricas {
  total_eventos: number;
  total_incidentes: number;
  incidentes_por_prioridade: Record<Prioridade, number>;
  incidentes_por_estado: Record<EstadoIncidente, number>;
  notificacoes_por_estado: Record<string, number>;
  taxa_reducao_eventos: number;
  tempo_medio_reconhecimento_s: number | null;
}

export interface SimulacaoDelta {
  critPagamentos: Criticidade;
  critWeb: Criticidade;
  limiarForcaBruta: number;
  sudoSempreAlto: boolean;
}
