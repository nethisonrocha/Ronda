"""Adaptador do Wazuh com alertas sintéticos que seguem a estrutura real (AIT-ADS e alerts.json).

Nada aqui é copiado do AIT-ADS (licença a conferir, D4 em docs/pendencias.md). IPs das faixas de
documentação.
"""

import copy
import importlib.util
import json
from datetime import UTC, datetime
from ipaddress import ip_address

import pytest

from ronda.adapters.base import AlertaInvalido
from ronda.adapters.wazuh import AdaptadorWazuh, Mapeamento, Via, iterar_jsonl
from ronda.domain.taxonomy import Categoria
from tests.conftest import RAIZ


def wazuh(**sobrescrever) -> dict:
    """Alerta do Wazuh como no AIT-ADS: JSON na raiz, com @timestamp."""
    alerta = {
        "predecoder": {"hostname": "mail", "program_name": "sshd"},
        "agent": {"ip": "192.0.2.10", "name": "wazuh-client", "id": "19"},
        "manager": {"name": "wazuh.manager"},
        "rule": {
            "firedtimes": 3,
            "level": 5,
            "description": "sshd: authentication failed.",
            "groups": ["syslog", "sshd", "authentication_failed"],
            "id": "5716",
            "mitre": {"id": ["T1110.001"], "tactic": ["Credential Access"]},
        },
        "data": {"srcip": "203.0.113.7", "srcport": "40022"},
        "decoder": {"name": "sshd"},
        "full_log": "Jan 21 00:02:27 mail sshd[123]: Failed password for root",
        "@timestamp": "2022-01-21T00:02:27.000000Z",
        "location": "/var/log/auth.log",
        "id": "1685715378.241",
    }
    for caminho, valor in sobrescrever.items():
        alvo = alerta
        *pais, folha = caminho.split("__")
        for pai in pais:
            alvo = alvo.setdefault(pai, {})
        if valor is None:
            alvo.pop(folha, None)
        else:
            alvo[folha] = valor
    return alerta


def suricata(
    assinatura="ET SCAN Possible Nmap User-Agent Observed", categoria="Web Application Attack"
):
    """Alerta do Suricata lido pelo Wazuh do eve.json (regra 86601)."""
    return {
        "agent": {"ip": "192.0.2.20", "name": "wazuh-client", "id": "16"},
        "data": {
            "src_ip": "203.0.113.7",
            "src_port": "44510",
            "dest_ip": "10.0.1.5",
            "dest_port": "80",
            "proto": "TCP",
            "event_type": "alert",
            "alert": {
                "severity": "1",
                "signature_id": "2024364",
                "signature": assinatura,
                "category": categoria,
                "action": "allowed",
            },
        },
        "rule": {
            "level": 3,
            "description": f"Suricata: Alert - {assinatura}",
            "groups": ["ids", "suricata"],
            "id": "86601",
        },
        "decoder": {"name": "json"},
        "@timestamp": "2022-01-21T00:14:21.351932Z",
        "location": "/var/log/suricata/eve.json",
        "id": "1685716093.15431",
    }


def fastlog(regra_id="20101"):
    """Cópia do mesmo alerta do Suricata, lida do fast.log pelo decoder snort."""
    return {
        "agent": {"ip": "192.0.2.20", "name": "wazuh-client", "id": "16"},
        "data": {"srcip": "203.0.113.7", "dstip": "10.0.1.5:80", "id": "1:2024364:6"},
        "rule": {"level": 3, "description": "IDS event.", "groups": ["ids"], "id": regra_id},
        "decoder": {"parent": "snort", "name": "snort"},
        "@timestamp": "2022-01-21T00:14:21.351932Z",
        "location": "/var/log/suricata/fast.log",
        "id": "1685716093.28059",
    }


@pytest.fixture(scope="module")
def adaptador():
    return AdaptadorWazuh()


def um(adaptador, alerta, tenant="demo"):
    eventos = adaptador.converter(alerta, tenant)
    assert len(eventos) == 1
    return eventos[0]


# --- mapeamento ------------------------------------------------------------------------


def test_mapping_yaml_esta_em_dia_com_a_taxonomia():
    spec = importlib.util.spec_from_file_location(
        "gerar_mapeamento_wazuh", RAIZ / "scripts" / "gerar_mapeamento_wazuh.py"
    )
    gerador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gerador)
    atual = (RAIZ / "src" / "ronda" / "adapters" / "wazuh" / "mapping.yaml").read_text("utf-8")
    assert atual == gerador.gerar(), "rode scripts/gerar_mapeamento_wazuh.py"


def test_mapping_do_pacote_carrega_e_segue_a_taxonomia():
    mapeamento = Mapeamento.carregar()
    assert mapeamento.wazuh.regras["31101"] is Categoria.reconhecimento  # exceção da taxonomia
    assert mapeamento.wazuh.regras["52507"] is Categoria.benigno  # ClamAV, apesar de "virus"
    assert (
        mapeamento.suricata.assinaturas["ET INFO Observed DNS Query to .biz TLD"]
        is Categoria.exfiltracao
    )
    assert "20161" in mapeamento.descartar.regras_fastlog


def test_mapping_com_categoria_inexistente_e_recusado(tmp_path):
    arquivo = tmp_path / "m.yaml"
    arquivo.write_text("versao: 1\ntaxonomia: x\nwazuh: {regras: {'1': phishing}}\n", "utf-8")
    with pytest.raises(ValueError, match="phishing"):
        Mapeamento.carregar(arquivo)


# --- Wazuh ---------------------------------------------------------------------------------


def test_wazuh_por_regra_exata(adaptador):
    evento = um(adaptador, wazuh(rule__id="31101", rule__groups=["web", "accesslog", "attack"]))
    assert evento.categoria is Categoria.reconhecimento  # a exata vence o grupo "attack"
    assert evento.evidencias["mapeamento"] == {"via": "exata", "chave": "wazuh.regras:31101"}


def test_wazuh_por_grupo_na_ordem_da_taxonomia(adaptador):
    # 5716 não está na taxonomia; o grupo authentication_failed decide.
    evento = um(adaptador, wazuh())
    assert evento.categoria is Categoria.forca_bruta
    assert evento.evidencias["mapeamento"]["via"] == Via.generica
    assert evento.evidencias["mapeamento"]["chave"] == "wazuh.grupos:authentication_failed"

    # sudo vem antes de authentication_success.
    sudo = um(adaptador, wazuh(rule__id="99999", rule__groups=["authentication_success", "sudo"]))
    assert sudo.categoria is Categoria.comprometimento


def test_wazuh_sem_mapeamento_vira_desconhecido(adaptador):
    evento = um(adaptador, wazuh(rule__id="99998", rule__groups=["syslog", "algo_novo"]))
    assert evento.categoria is Categoria.desconhecido
    assert evento.evidencias["mapeamento"] == {
        "via": "sem_mapeamento",
        "chave": "wazuh.regras:99998",
    }


def test_wazuh_campos_do_evento(adaptador):
    evento = um(adaptador, wazuh())
    assert evento.origem == "wazuh"
    assert evento.id_origem == "1685715378.241"
    assert evento.ocorrido_em == datetime(2022, 1, 21, 0, 2, 27, tzinfo=UTC)
    assert evento.severidade_origem == 5
    assert evento.ip_origem == ip_address("203.0.113.7")
    assert evento.ip_destino == ip_address("192.0.2.10")  # sem dstip, o destino é o agente
    assert evento.ativo == "mail"  # a máquina que gerou o log
    assert evento.evidencias["regra"]["mitre"] == ["T1110.001"]
    assert evento.evidencias["agente"] == {"id": "19", "name": "wazuh-client", "ip": "192.0.2.10"}
    assert evento.bruto["full_log"].startswith("Jan 21")


def test_sem_predecoder_o_ativo_e_o_agente(adaptador):
    evento = um(adaptador, wazuh(predecoder=None, agent__name="web01"))
    assert evento.ativo == "web01"


# --- Suricata pelo Wazuh -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("assinatura", "categoria", "esperado", "via"),
    [
        (
            "ET INFO Observed DNS Query to .biz TLD",
            "Potentially Bad Traffic",
            "exfiltracao",
            "exata",
        ),
        (
            "ET SCAN Behavioral Unusual Port 445 traffic",
            "Misc activity",
            "reconhecimento",
            "generica",
        ),
        ("ET POLICY Algo Novo", "Misc activity", "benigno", "generica"),
        ("SURICATA TLS algo novo", "Generic Protocol Command Decode", "desconhecido", "generica"),
        ("ET HUNTING Algo", "Categoria que não existe", "desconhecido", "sem_mapeamento"),
    ],
)
def test_suricata_assinatura_familia_categoria_ou_desconhecido(
    adaptador, assinatura, categoria, esperado, via
):
    evento = um(adaptador, suricata(assinatura, categoria))
    assert evento.categoria.value == esperado
    assert evento.evidencias["mapeamento"]["via"] == via


def test_suricata_campos_do_evento(adaptador):
    evento = um(adaptador, suricata())
    assert evento.origem == "suricata"
    assert evento.categoria is Categoria.reconhecimento  # ET SCAN vence "Web Application Attack"
    assert (evento.ip_origem, evento.ip_destino) == (
        ip_address("203.0.113.7"),
        ip_address("10.0.1.5"),
    )
    assert evento.ativo is None  # resolvido pelos IPs no inventário da política
    assert evento.severidade_origem == 1
    assert evento.evidencias["suricata"]["assinatura_id"] == 2024364
    assert evento.evidencias["suricata"]["porta_destino"] == 80


def test_copias_do_fastlog_sao_descartadas(adaptador):
    for regra in ("20100", "20101", "20151", "20152", "20161", "20162"):
        assert adaptador.converter(fastlog(regra), "demo") == []


def test_sem_descarte_a_copia_do_fastlog_vira_evento_com_ip_sem_porta():
    evento = um(AdaptadorWazuh(descartar_fastlog=False), fastlog())
    assert evento.categoria is Categoria.desconhecido  # 20101 não tem mapeamento
    assert evento.ip_destino == ip_address("10.0.1.5")  # "10.0.1.5:80" sem a porta


# --- formatos de entrada -------------------------------------------------------------------


def test_formato_do_alerts_json_e_do_webhook(adaptador):
    """Ao vivo, o alerta traz `timestamp` com fuso "+0000" e não tem @timestamp."""
    alerta = wazuh(**{"@timestamp": None, "timestamp": "2022-01-21T00:02:27.123+0000"})
    evento = um(adaptador, alerta)
    assert evento.ocorrido_em == datetime(2022, 1, 21, 0, 2, 27, 123000, tzinfo=UTC)


def test_envelope_do_indexador(adaptador):
    evento = um(adaptador, {"_index": "wazuh-alerts-4.x", "_id": "x", "_source": wazuh()})
    assert evento.id_origem == "1685715378.241"
    assert "_index" not in evento.bruto


def test_dstip_vence_o_ip_do_agente(adaptador):
    evento = um(adaptador, wazuh(data__dstip="198.51.100.9"))
    assert evento.ip_destino == ip_address("198.51.100.9")


def test_alerta_do_manager_sem_ip_de_agente(adaptador):
    evento = um(adaptador, wazuh(agent={"id": "000", "name": "wazuh.manager"}, predecoder=None))
    assert evento.ativo == "wazuh.manager"
    assert evento.ip_destino is None
    assert evento.evidencias["agente"] == {"id": "000", "name": "wazuh.manager"}


def test_ip_invalido_vira_ausente(adaptador):
    assert um(adaptador, wazuh(data__srcip="não-é-ip")).ip_origem is None
    assert um(adaptador, wazuh(data__srcip="[2001:db8::7]:443")).ip_origem == ip_address(
        "2001:db8::7"
    )


# --- identidade e erros --------------------------------------------------------------------


def test_mesmo_alerta_gera_o_mesmo_id_por_tenant(adaptador):
    a, b = um(adaptador, wazuh()), um(adaptador, copy.deepcopy(wazuh()))
    assert a.id == b.id
    assert um(adaptador, wazuh(), tenant="acme").id != a.id


def test_alerta_sem_id_recebe_id_pelo_conteudo(adaptador):
    """Reentrega da mesma mensagem não pode virar dois eventos, mesmo sem id na ferramenta."""
    a, b = um(adaptador, wazuh(id=None)), um(adaptador, wazuh(id=None))
    assert a.id == b.id and a.id_origem is None
    outro = um(adaptador, wazuh(id=None, full_log="outra linha"))
    assert outro.id != a.id


@pytest.mark.parametrize(
    ("alerta", "trecho"),
    [
        ({"@timestamp": "2022-01-21T00:02:27Z"}, "rule.id"),
        (wazuh(**{"@timestamp": None}), "timestamp"),
        (wazuh(**{"@timestamp": "ontem"}), "horário inválido"),
        (wazuh(**{"@timestamp": "2022-01-21T00:02:27"}), "sem fuso"),
    ],
)
def test_alerta_incompleto_e_recusado(adaptador, alerta, trecho):
    with pytest.raises(AlertaInvalido, match=trecho):
        adaptador.converter(alerta, "demo")


def test_tenant_invalido_e_recusado(adaptador):
    with pytest.raises(AlertaInvalido, match="não virou evento"):
        adaptador.converter(wazuh(), "../acme")


def test_iterar_jsonl(tmp_path):
    arquivo = tmp_path / "alertas.json"
    arquivo.write_text(
        json.dumps(wazuh()) + "\n\n" + json.dumps(suricata()) + "\n", encoding="utf-8"
    )
    assert [a["rule"]["id"] for a in iterar_jsonl(arquivo)] == ["5716", "86601"]

    arquivo.write_text("{quebrado\n", encoding="utf-8")
    with pytest.raises(AlertaInvalido, match=r"alertas\.json:1"):
        list(iterar_jsonl(arquivo))
