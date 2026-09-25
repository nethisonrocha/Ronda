"""Notificação de um incidente para um canal (Telegram na primeira versão)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field

from ronda.domain.event import TENANT_PATTERN
from ronda.domain.priority import Prioridade


class ModoNotificacao(StrEnum):
    imediata = "imediata"
    agrupada = "agrupada"
    resumo_diario = "resumo_diario"


class EstadoNotificacao(StrEnum):
    pendente = "pendente"
    enviada = "enviada"
    falhou = "falhou"
    suprimida = "suprimida"
    """Decidida pela política anti-fadiga: não sai, mas fica registrada com o motivo."""


class Notificacao(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(pattern=TENANT_PATTERN)
    incidente_id: UUID
    decisao_id: UUID | None = None
    canal: str = Field(min_length=1)
    destino: str = Field(min_length=1, description="Ex.: id do chat do Telegram")
    prioridade: Prioridade
    modo: ModoNotificacao
    estado: EstadoNotificacao = EstadoNotificacao.pendente
    motivo: str | None = Field(default=None, description="Motivo da supressão ou último erro")
    tentativas: int = Field(default=0, ge=0)
    id_externo: str | None = Field(default=None, description="Id da mensagem no canal")
    criada_em: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    enviada_em: AwareDatetime | None = None
    reconhecida_em: AwareDatetime | None = None
    reconhecida_por: str | None = None
