"""Adaptador do Wazuh: alertas do AIT-ADS, do alerts.json, do webhook e do indexador."""

from ronda.adapters.wazuh.adapter import (
    AdaptadorWazuh,
    Classificacao,
    Mapeamento,
    Via,
    iterar_jsonl,
)

__all__ = ["AdaptadorWazuh", "Classificacao", "Mapeamento", "Via", "iterar_jsonl"]
