"""Reavaliação da prioridade de um incidente. Pura: o motor não faz I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ronda.correlation.grouper import elevar
from ronda.domain.event import Evento
from ronda.domain.incident import Contexto
from ronda.domain.priority import Prioridade
from ronda.governance.engine import Decisao, Motor
from ronda.governance.policy import Politica


@dataclass(frozen=True)
class Reavaliacao:
    decisao: Decisao
    """A decisão do motor com o contexto novo (com rastro)."""
    prioridade: Prioridade
    """A prioridade efetiva do incidente: a da decisão, ou a atual, se a atual for mais grave."""
    subiu: bool
    """A prioridade efetiva mudou; é quando a decisão é gravada e a notificação avaliada."""


def montar_contexto(
    anterior: Contexto,
    politica: Politica,
    instante: datetime,
    recorrencia: int,
    ataque_previo: bool = False,
) -> Contexto:
    """O contexto do incidente depois de um evento: recorrência, expediente e ataque prévio.

    `confirmado` não muda aqui: vem da fonte ou do analista.
    """
    expediente = politica.expediente
    return anterior.model_copy(
        update={
            "recorrencia_24h": recorrencia,
            "fora_do_horario": expediente.fora(instante) if expediente else False,
            "ataque_previo_no_ativo": ataque_previo,
        }
    )


def precisa_reavaliar(novo: bool, anterior: Contexto, atual: Contexto) -> bool:
    """Reavalia quando o incidente nasce ou quando o contexto muda (a recorrência, sobretudo)."""
    return novo or anterior != atual


def reavaliar(
    motor: Motor, evento: Evento, contexto: Contexto, prioridade_atual: Prioridade | None
) -> Reavaliacao:
    decisao = motor.avaliar(evento, contexto)
    efetiva = elevar(prioridade_atual, decisao.prioridade)
    return Reavaliacao(decisao, efetiva, subiu=efetiva != prioridade_atual)
