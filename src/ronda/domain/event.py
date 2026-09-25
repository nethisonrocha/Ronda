"""Esquema único de evento: todo alerta vira isto, qualquer que seja a fonte."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field, IPvAnyAddress

from ronda.domain.taxonomy import Categoria

# Identificador de tenant: também vira nome de arquivo de política, então nada de
# barras, pontos ou maiúsculas.
TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"


class Evento(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(pattern=TENANT_PATTERN)
    origem: str = Field(min_length=1, description="Ferramenta que gerou o alerta")
    id_origem: str | None = Field(
        default=None, description="Id do alerta na ferramenta; torna a ingestão idempotente"
    )
    categoria: Categoria
    severidade_origem: int | str | None = Field(
        default=None, description="Severidade como a fonte reportou"
    )
    ip_origem: IPvAnyAddress | None = None
    ip_destino: IPvAnyAddress | None = None
    ativo: str | None = Field(
        default=None, description="Nome do ativo, quando a fonte já o conhece"
    )
    ocorrido_em: AwareDatetime
    evidencias: dict[str, Any] = Field(default_factory=dict)
    bruto: dict[str, Any] = Field(default_factory=dict, description="Alerta original")
