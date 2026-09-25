import json

import pytest
import redis
from fastapi.testclient import TestClient

from ronda.api.deps import banco_de_dados, cliente_redis
from ronda.api.main import app
from ronda.storage.repositories import RepositorioTokens
from ronda.workers.ingestao import STREAM
from tests.unit.adapters.test_wazuh import wazuh

URL = "/v1/ingestao/wazuh"


@pytest.fixture
def cliente(banco, redis_cliente):
    app.dependency_overrides[banco_de_dados] = lambda: banco
    app.dependency_overrides[cliente_redis] = lambda: redis_cliente
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def token(banco):
    with banco.sessao("demo") as sessao:
        valor, _ = RepositorioTokens(sessao).criar("teste")
    return valor


def autorizar(token):
    return {"Authorization": f"Bearer {token}"}


def test_um_alerta_vai_para_a_stream_com_o_tenant_do_token(cliente, token, redis_cliente):
    resposta = cliente.post(URL, json=wazuh(), headers=autorizar(token))
    assert resposta.status_code == 202 and resposta.json() == {"aceitos": 1}
    [(_, campos)] = redis_cliente.xrange(STREAM)
    assert campos["tenant"] == "demo" and campos["origem"] == "wazuh"
    assert json.loads(campos["alerta"])["id"] == "1685715378.241"
    assert token not in json.dumps(campos)  # o token nunca entra na mensagem


def test_lista_de_alertas_em_uma_requisicao(cliente, token, redis_cliente):
    lote = [wazuh(id=str(i)) for i in range(25)]
    assert cliente.post(URL, json=lote, headers=autorizar(token)).json() == {"aceitos": 25}
    assert redis_cliente.xlen(STREAM) == 25


@pytest.mark.parametrize(
    "cabecalhos",
    [{}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}, autorizar("rnd_inventado")],
)
def test_sem_token_valido_da_401_e_nada_entra_na_fila(cliente, redis_cliente, cabecalhos):
    resposta = cliente.post(URL, json=wazuh(), headers=cabecalhos)
    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"
    assert redis_cliente.exists(STREAM) == 0


def test_origem_desconhecida_e_corpo_invalido_dao_422(cliente, token):
    assert (
        cliente.post("/v1/ingestao/splunk", json=wazuh(), headers=autorizar(token)).status_code
        == 422
    )
    assert cliente.post(URL, json="texto", headers=autorizar(token)).status_code == 422
    assert cliente.post(URL, json=[], headers=autorizar(token)).status_code == 422


def test_lote_grande_demais_da_413(cliente, token):
    resposta = cliente.post(URL, json=[{"rule": {"id": "1"}}] * 1001, headers=autorizar(token))
    assert resposta.status_code == 413


def test_fila_fora_do_ar_da_503(banco, token):
    fora = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, decode_responses=True)
    app.dependency_overrides[banco_de_dados] = lambda: banco
    app.dependency_overrides[cliente_redis] = lambda: fora
    try:
        resposta = TestClient(app).post(URL, json=wazuh(), headers=autorizar(token))
    finally:
        app.dependency_overrides.clear()
    assert resposta.status_code == 503
