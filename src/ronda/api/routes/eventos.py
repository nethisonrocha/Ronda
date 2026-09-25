from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ronda.api.deps import obter_politica, repositorio_politicas
from ronda.domain.event import Evento
from ronda.domain.incident import Contexto
from ronda.governance.engine import Decisao, Motor
from ronda.governance.policy import RepositorioPoliticas

router = APIRouter(prefix="/eventos", tags=["eventos"])


class Avaliacao(BaseModel):
    evento: Evento
    contexto: Contexto = Field(default_factory=Contexto)


@router.post("/avaliar", response_model=Decisao)
def avaliar(
    entrada: Avaliacao,
    repositorio: Annotated[RepositorioPoliticas, Depends(repositorio_politicas)],
) -> Decisao:
    """Prioriza um evento com a política do tenant, sem persistir nada (fase 1)."""
    politica = obter_politica(repositorio, entrada.evento.tenant_id)
    return Motor(politica).avaliar(entrada.evento, entrada.contexto)
