"""Testes unitários do adaptador nativo do Suricata (eve.json)."""

from datetime import UTC, datetime
from ipaddress import ip_address

import pytest

from ronda.adapters.base import AlertaInvalido
from ronda.adapters.suricata import AdaptadorSuricata
from ronda.domain.taxonomy import Categoria
from tests.conftest import RAIZ


def eve_alerta(**sobrescrever) -> dict:
    alerta = {
        "timestamp": "2022-01-21T00:02:27.000000+0000",
        "flow_id": 1234567890,
        "event_type": "alert",
        "src_ip": "203.0.113.7",
        "src_port": 44510,
        "dest_ip": "10.0.1.5",
        "dest_port": 80,
        "proto": "TCP",
        "host": "sensor-borda",
        "alert": {
            "action": "allowed",
            "gid": 1,
            "signature_id": 2024364,
            "rev": 1,
            "signature": "ET SCAN Possible Nmap User-Agent Observed",
            "category": "Web Application Attack",
            "severity": 1,
        },
    }
    for chave, valor in sobrescrever.items():
        if "__" in chave:
            pai, folha = chave.split("__", 1)
            if valor is None:
                alerta[pai].pop(folha, None)
            else:
                alerta[pai][folha] = valor
        elif valor is None:
            alerta.pop(chave, None)
        else:
            alerta[chave] = valor
    return alerta


def test_converte_alerta_eve_valido():
    adaptador = AdaptadorSuricata()
    eventos = adaptador.converter(eve_alerta(), "demo")
    assert len(eventos) == 1
    ev = eventos[0]
    assert ev.tenant_id == "demo"
    assert ev.origem == "suricata"
    assert ev.categoria == Categoria.reconhecimento
    assert ev.severidade_origem == 1
    assert ev.ip_origem == ip_address("203.0.113.7")
    assert ev.ip_destino == ip_address("10.0.1.5")
    assert ev.ativo == "sensor-borda"
    assert ev.ocorrido_em == datetime(2022, 1, 21, 0, 2, 27, tzinfo=UTC)
    assert ev.evidencias["suricata"]["assinatura_id"] == 2024364
    assert ev.evidencias["suricata"]["porta_destino"] == 80
    assert ev.evidencias["suricata"]["flow_id"] == 1234567890
    assert ev.evidencias["mapeamento"]["via"] in {"exata", "generica"}


@pytest.mark.parametrize("tipo", ["flow", "dns", "http", "stats", None])
def test_ignora_eventos_que_nao_sao_alert(tipo):
    adaptador = AdaptadorSuricata()
    alerta = eve_alerta(event_type=tipo)
    assert adaptador.converter(alerta, "demo") == []
    assert adaptador.converter_um(alerta, "demo") is None


def test_classificacao_por_familia_et_e_desconhecido():
    adaptador = AdaptadorSuricata()
    et_web = adaptador.converter_um(
        eve_alerta(
            alert__signature="ET WEB_SERVER Possible SQL Injection Attempt",
            alert__category="Web Application Attack",
        ),
        "demo",
    )
    assert et_web is not None
    assert et_web.categoria == Categoria.ataque_web
    assert et_web.evidencias["mapeamento"]["via"] == "generica"

    desc = adaptador.converter_um(
        eve_alerta(
            alert__signature="CUSTOM Signature Sem Regra",
            alert__category="Custom Unknown Category",
        ),
        "demo",
    )
    assert desc is not None
    assert desc.categoria == Categoria.desconhecido
    assert desc.evidencias["mapeamento"]["via"] == "sem_mapeamento"


@pytest.mark.parametrize(
    "alteracao",
    [
        {"alert": None},
        {"alert__signature": None},
        {"alert__signature": ""},
        {"timestamp": None},
        {"timestamp": "invalido"},
    ],
)
def test_alerta_invalido_levanta_excecao(alteracao):
    adaptador = AdaptadorSuricata()
    with pytest.raises(AlertaInvalido):
        adaptador.converter_um(eve_alerta(**alteracao), "demo")


def test_id_deterministico_e_unico_por_assinatura():
    adaptador = AdaptadorSuricata()
    a1 = eve_alerta()
    a2 = eve_alerta()
    a3 = eve_alerta(alert__signature="ET WEB_SERVER Outra Assinatura", alert__signature_id=999999)

    ev1 = adaptador.converter_um(a1, "demo")
    ev2 = adaptador.converter_um(a2, "demo")
    ev3 = adaptador.converter_um(a3, "demo")
    assert ev1 is not None and ev2 is not None and ev3 is not None
    assert ev1.id == ev2.id
    assert ev1.id != ev3.id


def test_samples_suricata_quando_presente():
    from ronda.adapters.wazuh import iterar_jsonl

    amostra = RAIZ / "samples" / "demo_suricata.jsonl"
    if not amostra.exists():
        pytest.skip("samples/demo_suricata.jsonl ainda não gerado")
    adaptador = AdaptadorSuricata()
    eventos = [adaptador.converter_um(linha, "demo") for linha in iterar_jsonl(amostra)]
    assert len(eventos) >= 20
    assert all(ev is not None and ev.origem == "suricata" for ev in eventos)
