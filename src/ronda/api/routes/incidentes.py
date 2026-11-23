"""Rotas de consulta e operação sobre incidentes do tenant."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ronda.api.deps import banco_de_dados, tenant_do_token
from ronda.domain.event import Evento
from ronda.domain.incident import EstadoIncidente, Incidente
from ronda.domain.priority import Prioridade
from ronda.domain.taxonomy import Categoria
from ronda.storage.database import BancoDeDados
from ronda.storage.repositories import (
    DecisaoRegistrada,
    RepositorioAuditoria,
    RepositorioDecisoes,
    RepositorioEventos,
    RepositorioIncidentes,
)

router = APIRouter(prefix="/v1/incidentes", tags=["incidentes"])


class DetalheIncidente(BaseModel):
    incidente: Incidente
    decisoes: list[DecisaoRegistrada]
    eventos: list[Evento]


class ResultadoReconhecimento(BaseModel):
    reconhecido: bool
    incidente: Incidente


@router.get("", response_model=list[Incidente])
def listar_incidentes(
    tenant: Annotated[str, Depends(tenant_do_token)],
    banco: Annotated[BancoDeDados, Depends(banco_de_dados)],
    prioridade: Prioridade | None = None,
    estado: EstadoIncidente | None = None,
    categoria: Categoria | None = None,
    ativo: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[Incidente]:
    with banco.sessao(tenant) as sessao:
        return RepositorioIncidentes(sessao).listar(
            estado=estado,
            prioridade=prioridade,
            categoria=categoria,
            ativo=ativo,
            limite=limite,
            deslocamento=deslocamento,
        )


@router.get("/{incidente_id}", response_model=DetalheIncidente)
def obter_incidente(
    incidente_id: UUID,
    tenant: Annotated[str, Depends(tenant_do_token)],
    banco: Annotated[BancoDeDados, Depends(banco_de_dados)],
) -> DetalheIncidente:
    with banco.sessao(tenant) as sessao:
        incidente = RepositorioIncidentes(sessao).obter(incidente_id)
        if incidente is None:
            raise HTTPException(404, f"incidente {incidente_id} não encontrado")
        decisoes = RepositorioDecisoes(sessao).do_incidente(incidente_id)
        eventos = RepositorioEventos(sessao).do_incidente(incidente_id, limite=100)
        return DetalheIncidente(incidente=incidente, decisoes=decisoes, eventos=eventos)


@router.post("/{incidente_id}/reconhecer", response_model=ResultadoReconhecimento)
def reconhecer_incidente(
    incidente_id: UUID,
    tenant: Annotated[str, Depends(tenant_do_token)],
    banco: Annotated[BancoDeDados, Depends(banco_de_dados)],
) -> ResultadoReconhecimento:
    agora = datetime.now(UTC)
    with banco.sessao(tenant) as sessao:
        repo = RepositorioIncidentes(sessao)
        if repo.obter(incidente_id) is None:
            raise HTTPException(404, f"incidente {incidente_id} não encontrado")
        mudou = repo.reconhecer(incidente_id, agora)
        if mudou:
            RepositorioAuditoria(sessao).registrar(
                "api", "incidente.reconhecido", "incidente", incidente_id
            )
        atualizado = repo.obter(incidente_id)
        assert atualizado is not None
        return ResultadoReconhecimento(reconhecido=mudou, incidente=atualizado)
