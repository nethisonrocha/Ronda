"""Incidente e o contexto que a correlação calcula sobre ele.

Como no ITIL, evento e incidente são coisas diferentes: vários eventos com a
mesma origem, categoria e ativo dentro de uma janela viram um único incidente.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field

from ronda.domain.event import TENANT_PATTERN
from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria

JANELA_RECORRENCIA = timedelta(hours=24)
TETO_RECORRENCIA = 1000
"""A recorrência satura aqui: contar além disso custaria caro (um incidente de varredura passa
de 300 mil eventos) e nenhum modificador de política pode usar limiar maior."""


class Contexto(BaseModel):
    """Fatos sobre a situação que os modificadores de urgência da política podem usar."""

    recorrencia_24h: int = Field(
        default=0,
        ge=0,
        le=TETO_RECORRENCIA,
        description="Eventos com a mesma chave nas últimas 24 h, saturando em TETO_RECORRENCIA",
    )
    confirmado: bool = Field(default=False, description="Ataque confirmado pela fonte ou analista")
    fora_do_horario: bool = Field(default=False, description="Fora do expediente do tenant")


class EstadoIncidente(StrEnum):
    aberto = "aberto"
    reconhecido = "reconhecido"
    resolvido = "resolvido"


def chave_correlacao(origem: str, categoria: Categoria | str, ativo: str | None) -> str:
    """Identidade de um incidente ativo: mesma origem, categoria e ativo."""
    return f"{origem}|{Categoria(categoria).value}|{ativo or '-'}"


class Incidente(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(pattern=TENANT_PATTERN)
    origem: str = Field(min_length=1)
    categoria: Categoria
    ativo: str | None = None
    estado: EstadoIncidente = EstadoIncidente.aberto
    prioridade: Prioridade | None = None
    total_eventos: int = Field(default=0, ge=0)
    contexto: Contexto = Field(default_factory=Contexto)
    aberto_em: AwareDatetime
    atualizado_em: AwareDatetime
    reconhecido_em: AwareDatetime | None = None
    resolvido_em: AwareDatetime | None = None

    @property
    def chave_correlacao(self) -> str:
        return chave_correlacao(self.origem, self.categoria, self.ativo)
