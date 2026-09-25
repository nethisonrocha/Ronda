"""Rastro de decisão: cada etapa do motor deixa uma linha legível."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, computed_field


class Passo(BaseModel):
    etapa: str
    texto: str
    dados: dict[str, Any] = Field(default_factory=dict)


class Rastro(BaseModel):
    passos: list[Passo] = Field(default_factory=list)

    def registrar(self, etapa: str, texto: str, **dados: Any) -> None:
        self.passos.append(Passo(etapa=etapa, texto=texto, dados=dados))

    @computed_field
    @property
    def resumo(self) -> str:
        """Ex.: negacao_servico → ativo servidor-pagamentos (criticidade alta) → … → P1."""
        return " → ".join(passo.texto for passo in self.passos)


def formatar_duracao(duracao: timedelta) -> str:
    segundos = int(duracao.total_seconds())
    if segundos % 3600 == 0:
        return f"{segundos // 3600} h"
    return f"{segundos // 60} min"
