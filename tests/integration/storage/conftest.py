"""Fábricas dos testes do storage (os containers estão em tests/integration/conftest.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ronda.domain.incident import Incidente


@pytest.fixture
def incidente():
    """Fábrica de incidentes do tenant demo."""

    def fabricar(**campos) -> Incidente:
        agora = datetime(2026, 9, 25, 14, 3, 11, tzinfo=UTC)
        padrao = {
            "tenant_id": "demo",
            "origem": "wazuh",
            "categoria": "negacao_servico",
            "ativo": "servidor-pagamentos",
            "aberto_em": agora,
            "atualizado_em": agora,
        }
        return Incidente.model_validate(padrao | campos)

    return fabricar
