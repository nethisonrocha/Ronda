from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from ronda.config import carregar_config
from ronda.governance.policy import (
    Politica,
    PoliticaInvalida,
    PoliticaNaoEncontrada,
    RepositorioPoliticas,
)


@lru_cache
def repositorio_politicas() -> RepositorioPoliticas:
    return RepositorioPoliticas(carregar_config().policies_dir)


def obter_politica(repositorio: RepositorioPoliticas, tenant: str) -> Politica:
    try:
        return repositorio.obter(tenant)
    except PoliticaNaoEncontrada:
        raise HTTPException(404, f"nenhuma política para o tenant {tenant!r}") from None
    except PoliticaInvalida as erro:
        # Erro de configuração do servidor, não do cliente.
        raise HTTPException(500, str(erro)) from None
