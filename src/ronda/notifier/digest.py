"""Resumo diário dos incidentes P3: quando ele vence. Puro."""

from __future__ import annotations

from datetime import datetime, timedelta

from ronda.governance.policy import RegrasNotificacao


def momento_do_resumo(regras: RegrasNotificacao, agora: datetime) -> datetime:
    """O horário de resumo mais recente que já passou, em UTC (hoje ou ontem, no fuso do tenant)."""
    local = agora.astimezone(regras.zona)
    hoje = local.replace(
        hour=regras.resumo_diario.hour, minute=regras.resumo_diario.minute, second=0, microsecond=0
    )
    momento = hoje if hoje <= local else hoje - timedelta(days=1)
    return momento.astimezone(agora.tzinfo)


def resumo_vencido(
    regras: RegrasNotificacao,
    agora: datetime,
    ultimo_resumo: datetime | None,
    mais_antigo: datetime,
) -> bool:
    """Vence quando um horário de resumo passou depois do último resumo enviado (ou, se nunca
    houve resumo, depois do item pendente mais antigo)."""
    referencia = ultimo_resumo if ultimo_resumo is not None else mais_antigo
    return momento_do_resumo(regras, agora) > referencia
