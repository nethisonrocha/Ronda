"""Simulação de política: quantos eventos mudariam de prioridade com a versão nova."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from uuid import UUID

from pydantic import BaseModel

from ronda.domain.event import Evento
from ronda.domain.incident import Contexto
from ronda.domain.priority import Prioridade
from ronda.governance.engine import Motor
from ronda.governance.policy import Politica


class Mudanca(BaseModel):
    evento_id: UUID
    de: Prioridade
    para: Prioridade
    rastro_atual: str
    rastro_novo: str


class ResultadoSimulacao(BaseModel):
    versao_atual: int
    versao_nova: int
    total: int
    mudancas: list[Mudanca]
    transicoes: dict[str, int]
    """Contagem por transição, ex. {"P3→P1": 4}."""


def simular(
    itens: Iterable[tuple[Evento, Contexto]], atual: Politica, nova: Politica
) -> ResultadoSimulacao:
    if atual.tenant != nova.tenant:
        raise ValueError("as duas versões precisam ser do mesmo tenant")
    motor_atual, motor_novo = Motor(atual), Motor(nova)
    mudancas: list[Mudanca] = []
    transicoes: Counter[str] = Counter()
    total = 0
    for evento, contexto in itens:
        total += 1
        antes = motor_atual.avaliar(evento, contexto)
        depois = motor_novo.avaliar(evento, contexto)
        if antes.prioridade == depois.prioridade:
            continue
        mudancas.append(
            Mudanca(
                evento_id=evento.id,
                de=antes.prioridade,
                para=depois.prioridade,
                rastro_atual=antes.rastro.resumo,
                rastro_novo=depois.rastro.resumo,
            )
        )
        transicoes[f"{antes.prioridade.value}→{depois.prioridade.value}"] += 1
    return ResultadoSimulacao(
        versao_atual=atual.versao,
        versao_nova=nova.versao,
        total=total,
        mudancas=mudancas,
        transicoes=dict(sorted(transicoes.items())),
    )
