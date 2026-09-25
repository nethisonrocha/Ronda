from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import redis
from fastapi import Depends, Header, HTTPException

from ronda.config import obter_configuracao
from ronda.governance.policy import (
    Politica,
    PoliticaInvalida,
    PoliticaNaoEncontrada,
    RepositorioPoliticas,
)
from ronda.storage.database import BancoDeDados
from ronda.workers.ingestao import FilaIngestao


@lru_cache
def repositorio_politicas() -> RepositorioPoliticas:
    return RepositorioPoliticas(obter_configuracao().diretorio_politicas)


def obter_politica(repositorio: RepositorioPoliticas, tenant: str) -> Politica:
    try:
        return repositorio.obter(tenant)
    except PoliticaNaoEncontrada:
        raise HTTPException(404, f"nenhuma política para o tenant {tenant!r}") from None
    except PoliticaInvalida as erro:
        # Erro de configuração do servidor, não do cliente.
        raise HTTPException(500, str(erro)) from None


@lru_cache
def banco_de_dados() -> BancoDeDados:
    return BancoDeDados.da_configuracao(obter_configuracao())


@lru_cache
def cliente_redis() -> redis.Redis:
    url = obter_configuracao().url_redis
    if url is None:
        raise RuntimeError("defina RONDA_REDIS_URL (veja .env.example)")
    return redis.Redis.from_url(str(url), decode_responses=True)


def fila_ingestao(cliente: Annotated[redis.Redis, Depends(cliente_redis)]) -> FilaIngestao:
    return FilaIngestao(cliente)


def tenant_do_token(
    banco: Annotated[BancoDeDados, Depends(banco_de_dados)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Tenant do token `Authorization: Bearer <token>`. O token nunca vai para log nem erro."""
    esquema, _, token = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        raise HTTPException(
            401, "token de ingestão ausente", headers={"WWW-Authenticate": "Bearer"}
        )
    tenant = banco.tenant_do_token(token.strip())
    if tenant is None:
        raise HTTPException(
            401, "token de ingestão inválido", headers={"WWW-Authenticate": "Bearer"}
        )
    return tenant
