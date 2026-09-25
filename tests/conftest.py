from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ronda.domain.event import Evento
from ronda.governance.policy import Politica, carregar_politica

RAIZ = Path(__file__).resolve().parents[1]
POLITICAS_EXEMPLO = RAIZ / "policies" / "examples"


@pytest.fixture
def politica_demo() -> Politica:
    return carregar_politica(POLITICAS_EXEMPLO / "demo.yaml")


@pytest.fixture
def evento() -> Callable[..., Evento]:
    """Fábrica de eventos do tenant demo; os campos informados sobrescrevem o padrão."""

    def fabricar(**campos: Any) -> Evento:
        padrao: dict[str, Any] = {
            "tenant_id": "demo",
            "origem": "wazuh",
            "categoria": "negacao_servico",
            "ocorrido_em": datetime(2026, 9, 25, 14, 3, 11, tzinfo=UTC),
        }
        return Evento.model_validate(padrao | campos)

    return fabricar
