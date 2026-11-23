"""Rotas de métricas operacionais do tenant."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ronda.api.deps import banco_de_dados, tenant_do_token
from ronda.storage.database import BancoDeDados
from ronda.storage.repositories import RepositorioMetricas, ResumoMetricas

router = APIRouter(prefix="/v1/metricas", tags=["métricas"])


@router.get("/resumo", response_model=ResumoMetricas)
def resumo_metricas(
    tenant: Annotated[str, Depends(tenant_do_token)],
    banco: Annotated[BancoDeDados, Depends(banco_de_dados)],
) -> ResumoMetricas:
    with banco.sessao(tenant) as sessao:
        return RepositorioMetricas(sessao).resumo()
