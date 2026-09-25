"""Ingestão de alertas: autentica o tenant pelo token e publica no Redis Streams.

A rota não converte nem grava: só valida que chegou JSON de alerta e enfileira. Converter,
correlacionar e avaliar é trabalho do worker, fora do request.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from ronda.api.deps import fila_ingestao, tenant_do_token
from ronda.workers.ingestao import FilaIndisponivel, FilaIngestao

router = APIRouter(prefix="/v1/ingestao", tags=["ingestão"])

MAX_ALERTAS_POR_REQUISICAO = 1000
MAX_BYTES = 10 * 1024 * 1024


class Aceite(BaseModel):
    aceitos: int


@router.post("/{origem}", status_code=202, response_model=Aceite)
def ingerir(
    origem: Literal["wazuh"],
    request: Request,
    tenant: Annotated[str, Depends(tenant_do_token)],
    fila: Annotated[FilaIngestao, Depends(fila_ingestao)],
    corpo: Annotated[dict[str, Any] | list[dict[str, Any]], Body()],
) -> Aceite:
    """Um alerta (objeto JSON, como a integração do Wazuh envia) ou uma lista deles."""
    tamanho = request.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > MAX_BYTES:
        raise HTTPException(413, f"corpo acima de {MAX_BYTES // (1024 * 1024)} MB")
    alertas = corpo if isinstance(corpo, list) else [corpo]
    if not alertas:
        raise HTTPException(422, "nenhum alerta no corpo")
    if len(alertas) > MAX_ALERTAS_POR_REQUISICAO:
        raise HTTPException(413, f"no máximo {MAX_ALERTAS_POR_REQUISICAO} alertas por requisição")
    try:
        ids = fila.publicar(tenant, origem, alertas)
    except FilaIndisponivel:
        raise HTTPException(503, "fila indisponível; tente de novo") from None
    return Aceite(aceitos=len(ids))
