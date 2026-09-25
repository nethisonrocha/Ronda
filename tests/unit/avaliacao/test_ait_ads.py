import json

import pytest

from ronda.avaliacao.ait_ads import RotulosDesalinhados, alertas_rotulados, fases, inventario

CABECALHO = "time,name,ip,host,short,time_label,event_label\n"


def cenario(tmp_path, linhas_csv, alertas):
    (tmp_path / "csv").mkdir()
    (tmp_path / "json").mkdir()
    (tmp_path / "csv" / "teste_alerts.txt").write_text(
        CABECALHO + "".join(f"{linha}\n" for linha in linhas_csv), encoding="utf-8"
    )
    (tmp_path / "json" / "teste_wazuh.json").write_text(
        "".join(json.dumps(a) + "\n" for a in alertas), encoding="utf-8"
    )
    return tmp_path


def alerta(epoch_iso):
    return {"@timestamp": epoch_iso, "rule": {"id": "31101"}}


LINHAS = [
    "1642723347,Wazuh: A,172.19.130.4,mail,W-Sys-Cav,false_positive,-",
    "1642723350,AMiner: X,172.19.130.4,mail,A-Val,dirb,dirb",  # AMiner: fica fora
    "1642723352,Wazuh: B,10.143.2.4,intranet_server,W-Acc,dirb,dirb",
    "1642723360,Wazuh: C,192.168.231.56,davey_mail,W-Sys,cracking,-",
]
ALERTAS = [
    alerta("2022-01-21T00:02:27.000Z"),
    alerta("2022-01-21T00:02:32.000Z"),
    alerta("2022-01-21T00:02:40.000Z"),
]


def test_rotulos_casam_pela_posicao_sem_o_aminer(tmp_path):
    rotulados = list(alertas_rotulados(cenario(tmp_path, LINHAS, ALERTAS), "teste", 1))
    assert [(r.fase, r.causado) for _, r in rotulados] == [
        (None, False),
        ("dirb", True),
        ("cracking", False),
    ]


def test_horario_desalinhado_e_recusado(tmp_path):
    fora = [ALERTAS[0], alerta("2022-01-21T09:00:00.000Z"), ALERTAS[2]]
    with pytest.raises(RotulosDesalinhados, match="alerta 1"):
        list(alertas_rotulados(cenario(tmp_path, LINHAS, fora), "teste", 1))


def test_contagens_diferentes_sao_recusadas(tmp_path):
    with pytest.raises(RotulosDesalinhados, match="CSV tem mais"):
        list(alertas_rotulados(cenario(tmp_path, LINHAS, ALERTAS[:2]), "teste"))


def test_inventario_por_host_com_o_nome_do_wazuh(tmp_path):
    ativos = inventario(cenario(tmp_path, LINHAS, ALERTAS), "teste")
    assert ativos == [
        {"nome": "davey-mail", "rede": "192.168.231.56/32", "criticidade": "baixa"},
        {"nome": "intranet-server", "rede": "10.143.2.4/32", "criticidade": "alta"},
        {"nome": "mail", "rede": "172.19.130.4/32", "criticidade": "alta"},
    ]


def test_fases_na_ordem_em_que_comecam(tmp_path):
    assert fases(cenario(tmp_path, LINHAS, ALERTAS), "teste") == ["dirb", "cracking"]
