"""Processadores de mensagem do worker de ingestão."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ronda.adapters.wazuh import AdaptadorWazuh
from ronda.storage.database import BancoDeDados
from ronda.storage.repositories import RepositorioEventos
from ronda.workers.ingestao import Resultado


class GravarEventos:
    """Converte o alerta com o adaptador da origem e grava o evento (idempotente)."""

    def __init__(self, banco: BancoDeDados, adaptadores: Mapping[str, Any] | None = None) -> None:
        self.banco = banco
        self.adaptadores = adaptadores or {"wazuh": AdaptadorWazuh()}

    def __call__(self, tenant: str, origem: str, alerta: Mapping[str, Any]) -> Resultado:
        evento = self.adaptadores[origem].converter_um(alerta, tenant)
        if evento is None:
            return Resultado.ignorado
        with self.banco.sessao(tenant) as sessao:
            gravado = RepositorioEventos(sessao).registrar(evento)
        return Resultado.gravado if gravado else Resultado.duplicado
