from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ronda.api.deps import obter_politica, repositorio_politicas
from ronda.api.routes.eventos import Avaliacao
from ronda.governance.policy import Politica, PoliticaInvalida, RepositorioPoliticas, ler_politica
from ronda.governance.simulate import ResultadoSimulacao, simular

router = APIRouter(prefix="/politicas", tags=["políticas"])


@router.get("/{tenant}", response_model=Politica)
def ler(
    tenant: str,
    repositorio: Annotated[RepositorioPoliticas, Depends(repositorio_politicas)],
) -> Politica:
    return obter_politica(repositorio, tenant)


class PedidoSimulacao(BaseModel):
    politica: dict[str, Any]
    """A versão candidata, no mesmo formato do YAML."""
    eventos: list[Avaliacao]


@router.post("/{tenant}/simular", response_model=ResultadoSimulacao)
def simular_politica(
    tenant: str,
    pedido: PedidoSimulacao,
    repositorio: Annotated[RepositorioPoliticas, Depends(repositorio_politicas)],
) -> ResultadoSimulacao:
    atual = obter_politica(repositorio, tenant)
    try:
        nova = ler_politica(pedido.politica, "política candidata")
    except PoliticaInvalida as erro:
        raise HTTPException(422, str(erro)) from None
    if nova.tenant != tenant:
        raise HTTPException(422, f"a política candidata é do tenant {nova.tenant!r}")
    if any(item.evento.tenant_id != tenant for item in pedido.eventos):
        raise HTTPException(422, f"todos os eventos precisam ser do tenant {tenant!r}")
    return simular(((i.evento, i.contexto) for i in pedido.eventos), atual, nova)
