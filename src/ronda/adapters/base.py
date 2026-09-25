"""Contrato comum dos adaptadores: alerta bruto da ferramenta → eventos no esquema único."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from ronda.domain.event import Evento


class AlertaInvalido(ValueError):
    """O alerta não tem os campos mínimos para virar evento."""


class Adaptador(Protocol):
    origem: str

    def converter(self, alerta: Mapping[str, Any], tenant_id: str) -> list[Evento]:
        """Lista vazia quando o alerta é conhecido e deve ser ignorado."""
        ...
