from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ronda.api.deps import repositorio_politicas
from ronda.api.main import app
from ronda.governance.policy import RepositorioPoliticas
from tests.conftest import POLITICAS_EXEMPLO

EVENTO = {
    "tenant_id": "demo",
    "origem": "wazuh",
    "categoria": "negacao_servico",
    "severidade_origem": 10,
    "ip_origem": "203.0.113.7",
    "ip_destino": "10.0.1.5",
    "ocorrido_em": "2026-09-25T14:03:11Z",
    "evidencias": {"regra": 5712},
}


def cliente_com(diretorio: Path) -> TestClient:
    app.dependency_overrides[repositorio_politicas] = lambda: RepositorioPoliticas(diretorio)
    return TestClient(app)


@pytest.fixture
def cliente():
    yield cliente_com(POLITICAS_EXEMPLO)
    app.dependency_overrides.clear()


def test_saude(cliente):
    assert cliente.get("/saude").json()["status"] == "ok"


def test_avaliar_evento(cliente):
    resposta = cliente.post("/eventos/avaliar", json={"evento": EVENTO})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["prioridade"] == "P1"
    assert corpo["resposta"] == "PT15M"
    assert corpo["rastro"]["resumo"].startswith("negacao_servico → ativo servidor-pagamentos")


def test_avaliar_com_contexto(cliente):
    evento = EVENTO | {"categoria": "forca_bruta"}
    corpo = cliente.post(
        "/eventos/avaliar", json={"evento": evento, "contexto": {"recorrencia_24h": 50}}
    ).json()
    assert corpo["prioridade"] == "P2"


def test_tenant_sem_politica_da_404(cliente):
    resposta = cliente.post("/eventos/avaliar", json={"evento": EVENTO | {"tenant_id": "acme"}})
    assert resposta.status_code == 404


def test_evento_invalido_da_422(cliente):
    resposta = cliente.post("/eventos/avaliar", json={"evento": EVENTO | {"categoria": "phishing"}})
    assert resposta.status_code == 422


def test_politica_quebrada_no_servidor_da_500(tmp_path):
    (tmp_path / "demo.yaml").write_text("tenant: demo\nversao: 1\n", encoding="utf-8")
    try:
        resposta = cliente_com(tmp_path).post("/eventos/avaliar", json={"evento": EVENTO})
    finally:
        app.dependency_overrides.clear()
    assert resposta.status_code == 500
    assert "matriz" in resposta.json()["detail"]


def test_ler_politica(cliente):
    corpo = cliente.get("/politicas/demo").json()
    assert corpo["versao"] == 4
    assert corpo["resposta"]["P1"] == "PT15M"


def test_simular_politica(cliente):
    candidata = cliente.get("/politicas/demo").json()
    candidata["versao"] = 4
    candidata["matriz"]["alto"]["alta"] = "P2"
    resposta = cliente.post(
        "/politicas/demo/simular",
        json={"politica": candidata, "eventos": [{"evento": EVENTO}, {"evento": EVENTO}]},
    )
    assert resposta.status_code == 200
    assert resposta.json()["transicoes"] == {"P1→P2": 2}


def test_simular_recusa_candidata_invalida(cliente):
    resposta = cliente.post(
        "/politicas/demo/simular", json={"politica": {"tenant": "demo"}, "eventos": []}
    )
    assert resposta.status_code == 422
