"""Incidente e o contexto que a correlação calcula sobre ele.

Como no ITIL, evento e incidente são coisas diferentes: vários eventos com a
mesma origem, categoria e ativo dentro de uma janela viram um único incidente.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field

from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria


class Contexto(BaseModel):
    """Fatos sobre a situação que os modificadores de urgência da política podem usar."""

    recorrencia_24h: int = Field(default=0, ge=0, description="Eventos iguais nas últimas 24 h")
    confirmado: bool = Field(default=False, description="Ataque confirmado pela fonte ou analista")
    fora_do_horario: bool = Field(default=False, description="Fora do expediente do tenant")


class Incidente(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    origem: str
    categoria: Categoria
    ativo: str | None = None
    eventos: list[UUID] = Field(default_factory=list)
    aberto_em: AwareDatetime
    atualizado_em: AwareDatetime
    prioridade: Prioridade | None = None
    contexto: Contexto = Field(default_factory=Contexto)
