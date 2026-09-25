"""Ponta a ponta: replay → API → Redis Streams → worker → pipeline → banco."""

from datetime import UTC, datetime, timedelta
from itertools import islice

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ronda.adapters.wazuh.adapter import horario_do_alerta, iterar_jsonl
from ronda.api.deps import banco_de_dados, cliente_redis
from ronda.api.main import app
from ronda.governance.policy import RepositorioPoliticas
from ronda.replay import enviar_por_http, reproduzir
from ronda.storage.repositories import RepositorioTokens
from ronda.workers.ingestao import STREAM, WorkerIngestao
from ronda.workers.pipeline import Pipeline
from tests.conftest import POLITICAS_EXEMPLO, RAIZ
from tests.unit.adapters.test_wazuh import fastlog, suricata, wazuh

RUSSELLMITCHELL = RAIZ / "data" / "raw" / "ait-ads" / "json" / "russellmitchell_wazuh.json"


@pytest.fixture
def ambiente(banco, redis_cliente):
    app.dependency_overrides[banco_de_dados] = lambda: banco
    app.dependency_overrides[cliente_redis] = lambda: redis_cliente
    with banco.sessao("demo") as sessao:
        token, _ = RepositorioTokens(sessao).criar("replay")
    pipeline = Pipeline(banco, RepositorioPoliticas(POLITICAS_EXEMPLO))
    worker = WorkerIngestao(
        redis_cliente,
        pipeline,
        bloquear_ms=100,
        lote=500,
        depois_do_lote=pipeline.encerrar_inativos,
    )
    worker.garantir_grupo()
    yield TestClient(app), token, worker
    app.dependency_overrides.clear()


def replay_e_consumo(ambiente, alertas, redis_cliente):
    cliente, token, worker = ambiente
    enviar = enviar_por_http(cliente, "/v1/ingestao/wazuh", token)
    resultado = reproduzir(((horario_do_alerta(a), a) for a in alertas), enviar, 0)
    while redis_cliente.xlen(STREAM):
        worker.processar_lote(bloquear=False)
    return resultado


def contar(dono, sql):
    with dono.connect() as conexao:
        return conexao.execute(text(sql)).scalar()


def test_ponta_a_ponta_sintetico(ambiente, redis_cliente, dono):
    t0 = datetime(2022, 1, 21, 10, 0, tzinfo=UTC)
    alertas = []
    for i in range(8):  # oito falhas de SSH no mesmo host, a cada 2 min: um incidente
        alertas.append(
            wazuh(id=f"ssh-{i}", **{"@timestamp": (t0 + timedelta(minutes=2 * i)).isoformat()})
        )
    alertas.append(suricata())
    alertas.append(fastlog())  # cópia do Suricata: descartada
    replay_e_consumo(ambiente, alertas, redis_cliente)

    assert contar(dono, "SELECT count(*) FROM eventos") == 9
    assert contar(dono, "SELECT count(*) FROM incidentes") == 2
    assert contar(dono, "SELECT max(total_eventos) FROM incidentes") == 8
    # Toda decisão tem rastro e aponta para o incidente; cada incidente tem ao menos uma.
    assert contar(dono, "SELECT count(*) FROM decisoes WHERE jsonb_array_length(rastro) = 0") == 0
    assert (
        contar(
            dono,
            "SELECT count(*) FROM incidentes i WHERE NOT EXISTS "
            "(SELECT 1 FROM decisoes d WHERE d.tenant_id = i.tenant_id AND d.incidente_id = i.id)",
        )
        == 0
    )


@pytest.mark.skipif(
    not RUSSELLMITCHELL.exists(), reason="AIT-ADS não baixado (veja data/README.md)"
)
def test_ponta_a_ponta_trecho_do_russellmitchell(ambiente, redis_cliente, dono):
    alertas = list(islice(iterar_jsonl(RUSSELLMITCHELL), 2000))
    resultado = replay_e_consumo(ambiente, alertas, redis_cliente)

    eventos = contar(dono, "SELECT count(*) FROM eventos")
    incidentes = contar(dono, "SELECT count(*) FROM incidentes")
    decisoes = contar(dono, "SELECT count(*) FROM decisoes")
    assert resultado.alertas == 2000
    assert eventos == 1504  # 2000 alertas menos as 496 cópias do fast.log
    assert 0 < incidentes < eventos / 5  # a correlação reduz de verdade
    assert incidentes <= decisoes <= incidentes * 4  # decisão nova só quando a prioridade sobe
    assert contar(dono, "SELECT count(*) FROM decisoes WHERE jsonb_array_length(rastro) = 0") == 0
    assert contar(dono, "SELECT count(*) FROM eventos WHERE incidente_id IS NULL") == 0
    assert redis_cliente.xpending(STREAM, "ronda-ingestao")["pending"] == 0
