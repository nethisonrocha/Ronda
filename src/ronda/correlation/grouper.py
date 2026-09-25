"""Correlação: eventos viram incidentes. Lógica pura, sem I/O.

Regras (ADR 0003):

- **Chave.** Eventos com a mesma origem, categoria e ativo pertencem ao mesmo fluxo. O ativo é o
  do inventário da política; sem ele, o nome informado pela fonte e, por último, o IP de destino
  ou de origem.
- **Janela.** Um evento se junta ao incidente ativo da chave se chegar até `janela` depois do
  último evento dele (o intervalo é entre eventos, não desde a abertura). Passada a janela sem
  evento novo, o incidente se encerra por inatividade, no instante `último evento + janela`.
- **Recorrência.** Eventos da mesma chave nas últimas 24 h (qualquer incidente), saturando em
  `TETO_RECORRENCIA`.
- **Prioridade.** Reavaliada pelo motor quando a recorrência muda ou o incidente nasce; nunca
  diminui enquanto o incidente estiver aberto.

O tempo é sempre o do evento (`ocorrido_em`), nunca o relógio do servidor: um replay de 2022
precisa correlacionar como correlacionou em 2022.
"""

from __future__ import annotations

from bisect import insort
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from ronda.domain.event import Evento
from ronda.domain.incident import (
    JANELA_RECORRENCIA,
    TETO_RECORRENCIA,
    EstadoIncidente,
    Incidente,
    chave_correlacao,
)
from ronda.domain.priority import Prioridade


def ativo_de_correlacao(evento: Evento, ativo_do_inventario: str | None) -> str | None:
    """O ativo que entra na chave: inventário, depois o nome da fonte, depois os IPs."""
    if ativo_do_inventario:
        return ativo_do_inventario
    if evento.ativo:
        return evento.ativo
    ip = evento.ip_destino or evento.ip_origem
    return str(ip) if ip is not None else None


def chave_do_evento(evento: Evento, ativo_do_inventario: str | None = None) -> str:
    return chave_correlacao(
        evento.origem, evento.categoria, ativo_de_correlacao(evento, ativo_do_inventario)
    )


class Acao(StrEnum):
    agregar = "agregar"
    abrir = "abrir"


@dataclass(frozen=True)
class Agrupamento:
    acao: Acao
    encerrar_anterior_em: datetime | None = None
    """Quando o incidente ativo passou da janela: o instante em que ele se encerrou."""


def agrupar(instante: datetime, ativo: Incidente | None, janela: timedelta) -> Agrupamento:
    """Decide o destino de um evento dado o incidente ativo da chave (ou nenhum)."""
    if ativo is None or ativo.estado is EstadoIncidente.resolvido:
        return Agrupamento(Acao.abrir)
    if instante - ativo.atualizado_em <= janela:
        return Agrupamento(Acao.agregar)
    return Agrupamento(Acao.abrir, encerrar_anterior_em=ativo.atualizado_em + janela)


def encerrados_por_inatividade(
    incidentes: Iterable[Incidente], marca: datetime, janela: timedelta
) -> list[tuple[Incidente, datetime]]:
    """Incidentes ativos cuja janela passou antes da marca (o evento mais recente visto)."""
    return [
        (i, i.atualizado_em + janela)
        for i in incidentes
        if i.estado is not EstadoIncidente.resolvido and i.atualizado_em + janela < marca
    ]


def contar_recorrencia(
    instantes: Iterable[datetime],
    ate: datetime,
    janela: timedelta = JANELA_RECORRENCIA,
    teto: int = TETO_RECORRENCIA,
) -> int:
    """Eventos em (ate − janela, ate], saturando no teto."""
    inicio = ate - janela
    return min(teto, sum(1 for i in instantes if inicio < i <= ate))


def elevar(atual: Prioridade | None, nova: Prioridade) -> Prioridade:
    """A prioridade de um incidente aberto só sobe (P1 é a mais grave)."""
    if atual is None or nova.nivel < atual.nivel:
        return nova
    return atual


def novo_incidente(evento: Evento, ativo: str | None) -> Incidente:
    return Incidente(
        tenant_id=evento.tenant_id,
        origem=evento.origem,
        categoria=evento.categoria,
        ativo=ativo,
        aberto_em=evento.ocorrido_em,
        atualizado_em=evento.ocorrido_em,
    )


# --- correlação em memória -------------------------------------------------------------------


@dataclass
class _Fluxo:
    """Estado de uma chave: o incidente ativo e os instantes recentes para a recorrência."""

    incidente_id: UUID | None = None
    aberto_em: datetime | None = None
    atualizado_em: datetime | None = None
    total: int = 0
    recentes: deque[datetime] = field(default_factory=lambda: deque(maxlen=TETO_RECORRENCIA))


@dataclass(frozen=True)
class Observacao:
    incidente_id: UUID
    novo: bool
    recorrencia: int
    encerrado: tuple[UUID, datetime] | None
    """O incidente anterior da chave, se o evento chegou depois da janela."""


class CorrelacaoEmMemoria:
    """A mesma regra do worker, sem banco: para avaliação em lote e testes de propriedade.

    Espera eventos em ordem de tempo por chave (como vêm da ferramenta). Fora de ordem, o evento
    se junta ao incidente ativo se estiver dentro da janela, e a recorrência continua correta.
    """

    def __init__(self, janela: timedelta, teto: int = TETO_RECORRENCIA) -> None:
        self.janela = janela
        self.teto = teto
        self._fluxos: dict[str, _Fluxo] = {}

    def observar(self, chave: str, instante: datetime) -> Observacao:
        fluxo = self._fluxos.setdefault(chave, _Fluxo(recentes=deque(maxlen=self.teto)))
        encerrado = None
        novo = False
        ativo = fluxo.incidente_id is not None and fluxo.atualizado_em is not None
        if ativo and instante - fluxo.atualizado_em <= self.janela:
            fluxo.atualizado_em = max(fluxo.atualizado_em, instante)
            fluxo.total += 1
        else:
            if ativo:
                encerrado = (fluxo.incidente_id, fluxo.atualizado_em + self.janela)
            fluxo.incidente_id, fluxo.aberto_em, fluxo.atualizado_em = uuid4(), instante, instante
            fluxo.total, novo = 1, True
        if fluxo.recentes and instante < fluxo.recentes[-1]:
            ordenados = list(fluxo.recentes)
            insort(ordenados, instante)
            fluxo.recentes = deque(ordenados[-self.teto :], maxlen=self.teto)
        else:
            fluxo.recentes.append(instante)
        recorrencia = contar_recorrencia(fluxo.recentes, instante, teto=self.teto)
        return Observacao(fluxo.incidente_id, novo, recorrencia, encerrado)

    def encerrar_inativos(self, marca: datetime) -> list[tuple[UUID, datetime]]:
        encerrados = []
        for fluxo in self._fluxos.values():
            if fluxo.incidente_id and fluxo.atualizado_em + self.janela < marca:
                encerrados.append((fluxo.incidente_id, fluxo.atualizado_em + self.janela))
                fluxo.incidente_id = fluxo.aberto_em = fluxo.atualizado_em = None
                fluxo.total = 0
        return encerrados
