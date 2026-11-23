"""Adaptador do Suricata pelo eve.json nativo → `Evento`.

Aceita objetos JSON Lines do `eve.json`. Apenas registros com `event_type == "alert"`
viram eventos; outros tipos (`flow`, `dns`, `http`, `stats`, etc.) são ignorados.
Reutiliza as regras de classificação Suricata de `mapping.yaml`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ronda.adapters.base import AlertaInvalido
from ronda.adapters.wazuh.adapter import (
    AdaptadorWazuh,
    Mapeamento,
    _horario,
    _inteiro,
    _ip,
)
from ronda.domain.event import Evento


class AdaptadorSuricata:
    origem = "suricata"

    def __init__(self, mapeamento: Mapeamento | None = None) -> None:
        self.mapeamento = mapeamento or Mapeamento.carregar()

    def converter(self, alerta: Mapping[str, Any], tenant_id: str) -> list[Evento]:
        """Um evento por alerta; lista vazia quando não for `event_type == 'alert'`."""
        return [evento] if (evento := self.converter_um(alerta, tenant_id)) else []

    def converter_um(self, alerta: Mapping[str, Any], tenant_id: str) -> Evento | None:
        if alerta.get("event_type") != "alert":
            return None

        suricata = alerta.get("alert")
        if not isinstance(suricata, Mapping) or not suricata.get("signature"):
            raise AlertaInvalido("alerta Suricata sem alert.signature")

        horario = _horario(alerta.get("timestamp") or alerta.get("@timestamp"))
        assinatura = str(suricata["signature"])
        classificacao = self.mapeamento.classificar_suricata(assinatura, suricata.get("category"))
        severidade = _inteiro(suricata.get("severity"))

        host = alerta.get("host")
        ativo = host.strip() if isinstance(host, str) and host.strip() else None

        evidencias: dict[str, Any] = {
            "suricata": {
                "assinatura": assinatura,
                "assinatura_id": _inteiro(suricata.get("signature_id")),
                "categoria": suricata.get("category"),
                "severidade": severidade,
                "acao": suricata.get("action"),
                "protocolo": alerta.get("proto"),
                "porta_origem": _inteiro(alerta.get("src_port")),
                "porta_destino": _inteiro(alerta.get("dest_port")),
            },
            "mapeamento": {"via": classificacao.via.value, "chave": classificacao.chave},
        }
        if alerta.get("flow_id") is not None:
            evidencias["suricata"]["flow_id"] = _inteiro(alerta.get("flow_id"))

        id_origem = str(alerta["id"]) if alerta.get("id") else None
        try:
            return Evento(
                id=AdaptadorWazuh._id(tenant_id, self.origem, id_origem, alerta),
                tenant_id=tenant_id,
                origem=self.origem,
                id_origem=id_origem,
                categoria=classificacao.categoria,
                severidade_origem=severidade,
                ip_origem=_ip(alerta.get("src_ip")),
                ip_destino=_ip(alerta.get("dest_ip")),
                ativo=ativo,
                ocorrido_em=horario,
                evidencias=evidencias,
                bruto=dict(alerta),
            )
        except ValidationError as erro:
            raise AlertaInvalido(f"alerta Suricata não virou evento: {erro}") from erro
