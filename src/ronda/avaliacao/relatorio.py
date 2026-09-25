"""Avaliação de um cenário do AIT-ADS: roda o simulador e resume os números.

Duas perguntas:

1. **Redução.** Quantos eventos viram quantos incidentes, e quantos incidentes viram mensagem.
2. **Cobertura das fases.** Pelos rótulos de tempo, cada fase do ataque gerou pelo menos um
   incidente P1 ou P2? Mede-se de dois jeitos, porque o `time_label` sozinho engana: um incidente
   de rotina que atravessa a janela de uma fase "contém" a fase sem ter nada a ver com ela.
   - **pela janela:** algum incidente P1/P2 tem um evento com o `time_label` da fase;
   - **pela causa:** algum incidente P1/P2 tem um evento da fase que o ataque causou
     (`event_label` diferente de `-`);
   - **gerou:** o evento que levou o incidente a P1/P2 é da fase. É a leitura estrita: um
     incidente de DNS que já era P1 dias antes do ataque "contém" todas as fases, mas não foi
     gerado por nenhuma, e ninguém recebe aviso novo quando a fase acontece.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from ronda.adapters.wazuh import AdaptadorWazuh
from ronda.avaliacao.ait_ads import alertas_rotulados, fases, inventario
from ronda.avaliacao.simulador import IncidenteSimulado, Simulador
from ronda.domain.priority import Prioridade
from ronda.governance.policy import Politica, ler_politica

GRAVES = (Prioridade.P1, Prioridade.P2)


def politica_do_cenario(caminho: Path, diretorio: Path, cenario: str) -> Politica:
    """A política de avaliação com o inventário do cenário."""
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    dados["ativos"] = inventario(diretorio, cenario)
    return ler_politica(dados, f"{caminho} + inventário de {cenario}")


@dataclass
class ResultadoCenario:
    cenario: str
    alertas: int
    descartados: int
    """Cópias do Suricata vindas do fast.log (o adaptador descarta)."""
    fases: list[str]
    simulador: Simulador
    segundos: float

    @property
    def incidentes(self) -> list[IncidenteSimulado]:
        return list(self.simulador.incidentes.values())

    def resumo(self) -> dict[str, Any]:
        c = self.simulador.contagens
        incidentes = self.incidentes
        por_prioridade = {p.value: 0 for p in Prioridade}
        for i in incidentes:
            if i.prioridade is not None:
                por_prioridade[i.prioridade.value] += 1
        notificacoes = sum(
            v for (_, estado, _), v in c.notificacoes.items() if estado != "suprimida"
        )
        suprimidas = sum(v for (_, estado, _), v in c.notificacoes.items() if estado == "suprimida")
        mensagens = sum(c.mensagens.values())
        mensagens_graves = sum(v for (_, p), v in c.mensagens.items() if p in ("P1", "P2"))
        graves = [i for i in incidentes if i.prioridade in GRAVES]
        return {
            "cenario": self.cenario,
            "alertas": self.alertas,
            "eventos": c.eventos,
            "incidentes": len(incidentes),
            "decisoes": c.decisoes,
            **{f"incidentes_{p}": n for p, n in por_prioridade.items()},
            "notificacoes": notificacoes,
            "suprimidas": suprimidas,
            "so_painel": sum(c.sem_aviso.values()),
            "mensagens": mensagens,
            "mensagens_P1_P2": mensagens_graves,
            "mensagens_resumo": sum(v for (t, _), v in c.mensagens.items() if t == "resumo"),
            "eventos_por_incidente": round(c.eventos / max(1, len(incidentes)), 1),
            "eventos_por_mensagem": round(c.eventos / max(1, mensagens)),
            # Pelo evento que levou o incidente a P1/P2: causado pelo ataque, só dentro da janela
            # de uma fase, ou fora de qualquer ataque (ruído que acorda alguém).
            "graves_pela_causa": sum(1 for i in graves if _subida(i) == "causa"),
            "graves_na_janela": sum(1 for i in graves if _subida(i) == "janela"),
            "graves_fora_de_ataque": sum(1 for i in graves if _subida(i) == "fora"),
            "segundos": round(self.segundos),
        }

    def graves(self) -> list[dict[str, Any]]:
        """Os incidentes P1 e P2: os que acordariam alguém."""
        return [
            {
                "cenario": self.cenario,
                "prioridade": _prioridade(i),
                "categoria": i.categoria.value,
                "ativo": i.ativo,
                "origem": i.origem,
                "eventos": i.total,
                "aberto_em": i.aberto_em,
                "fases": ", ".join(sorted(i.eventos_por_fase)) or "-",
                "causados": sum(i.causados_por_fase.values()),
                "grave_em": i.grave_em,
                "subida": _subida(i),
                "fase_da_subida": i.rotulo_da_subida.fase if i.rotulo_da_subida else None,
            }
            for i in sorted(self.incidentes, key=lambda i: i.aberto_em)
            if i.prioridade in GRAVES
        ]

    def mensagens_detalhadas(self) -> dict[str, int]:
        return {f"{t}:{p}": v for (t, p), v in sorted(self.simulador.contagens.mensagens.items())}

    def espera(self) -> dict[str, dict[str, str]]:
        """Do registro da notificação ao envio: mediana e máxima por prioridade."""
        saida = {}
        for prioridade, esperas in sorted(self.simulador.contagens.espera.items()):
            saida[prioridade] = {
                "enviadas": str(len(esperas)),
                "mediana": _curta(median(esperas)),
                "maxima": _curta(max(esperas)),
            }
        return saida

    def cobertura(self) -> list[dict[str, Any]]:
        linhas = []
        for fase in self.fases:
            na_janela = [i for i in self.incidentes if i.eventos_por_fase[fase]]
            causados = [i for i in na_janela if i.causados_por_fase[fase]]
            melhor_janela = _mais_grave(na_janela)
            melhor_causa = _mais_grave(causados)
            gerados = [i for i in self.incidentes if _fase_da_subida(i) == fase]
            gerados_pela_causa = [i for i in gerados if _subida(i) == "causa"]
            gerado = _mais_grave(gerados_pela_causa) or _mais_grave(gerados)
            linhas.append(
                {
                    "cenario": self.cenario,
                    "fase": fase,
                    "gerou": "causa" if gerados_pela_causa else ("janela" if gerados else "-"),
                    "diagnostico": _diagnostico(
                        bool(gerados_pela_causa), bool(gerados), melhor_causa, causados
                    ),
                    "eventos": sum(i.eventos_por_fase[fase] for i in na_janela),
                    "causados": sum(i.causados_por_fase[fase] for i in causados),
                    "pela_janela": _prioridade(melhor_janela),
                    "pela_causa": _prioridade(melhor_causa),
                    "incidente_janela": _descrever(melhor_janela),
                    "incidente_causa": _descrever(melhor_causa),
                    "incidente_gerado": _descrever(gerado),
                }
            )
        return linhas


def _fase_da_subida(incidente: IncidenteSimulado) -> str | None:
    return incidente.rotulo_da_subida.fase if incidente.rotulo_da_subida else None


def _subida(incidente: IncidenteSimulado) -> str:
    """De onde veio o evento que levou o incidente a P1/P2."""
    rotulo = incidente.rotulo_da_subida
    if rotulo is None or rotulo.fase is None:
        return "fora"
    return "causa" if rotulo.causado else "janela"


def _diagnostico(
    gerou_pela_causa: bool,
    gerou_na_janela: bool,
    melhor_causa: IncidenteSimulado | None,
    causados: list[IncidenteSimulado],
) -> str:
    """A resposta à pergunta "a fase gerou um P1/P2?", da mais forte à mais fraca."""
    if gerou_pela_causa:
        return "gerou P1/P2"
    if melhor_causa is not None and melhor_causa.prioridade in GRAVES:
        return "caiu num P1/P2 que já existia"
    if gerou_na_janela:
        return "P1/P2 na janela, sem causa"
    if causados:
        return f"vista, mas {_prioridade(melhor_causa)}"
    return "sem alerta causado pelo ataque"


def _mais_grave(incidentes: list[IncidenteSimulado]) -> IncidenteSimulado | None:
    com_prioridade = [i for i in incidentes if i.prioridade is not None]
    if not com_prioridade:
        return None
    return min(com_prioridade, key=lambda i: (i.prioridade.nivel, -i.total))


def _prioridade(incidente: IncidenteSimulado | None) -> str:
    return incidente.prioridade.value if incidente and incidente.prioridade else "-"


def _descrever(incidente: IncidenteSimulado | None) -> str:
    if incidente is None:
        return "-"
    return f"{incidente.categoria.value} em {incidente.ativo or '?'} ({incidente.origem})"


def _curta(duracao: timedelta) -> str:
    segundos = int(duracao.total_seconds())
    if segundos < 60:
        return f"{segundos} s"
    if segundos < 3600:
        return f"{segundos // 60} min"
    return f"{segundos // 3600} h {segundos % 3600 // 60:02d} min"


def avaliar_cenario(
    diretorio: Path,
    cenario: str,
    caminho_politica: Path,
    adaptador: AdaptadorWazuh | None = None,
) -> ResultadoCenario:
    politica = politica_do_cenario(caminho_politica, diretorio, cenario)
    adaptador = adaptador or AdaptadorWazuh()
    simulador = Simulador(politica)
    inicio = time.perf_counter()
    alertas = descartados = 0
    for alerta, rotulo in alertas_rotulados(diretorio, cenario):
        alertas += 1
        evento = adaptador.converter_um(alerta, politica.tenant)
        if evento is None:
            descartados += 1
            continue
        simulador.processar(evento, rotulo)
    simulador.finalizar()
    return ResultadoCenario(
        cenario=cenario,
        alertas=alertas,
        descartados=descartados,
        fases=fases(diretorio, cenario),
        simulador=simulador,
        segundos=time.perf_counter() - inicio,
    )
