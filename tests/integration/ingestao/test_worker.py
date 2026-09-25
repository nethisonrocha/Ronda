import json

import pytest

from ronda.storage.repositories import RepositorioEventos
from ronda.workers.ingestao import STREAM, STREAM_ERROS, FilaIngestao, Resultado, WorkerIngestao
from ronda.workers.processadores import GravarEventos
from tests.unit.adapters.test_wazuh import fastlog, suricata, wazuh


def novo_worker(redis_cliente, processar, **opcoes):
    worker = WorkerIngestao(redis_cliente, processar, bloquear_ms=100, **opcoes)
    worker.garantir_grupo()
    return worker


def eventos_do_demo(banco):
    with banco.sessao("demo") as sessao:
        return RepositorioEventos(sessao).listar(limite=1000)


def pendentes(redis_cliente):
    return redis_cliente.xpending(STREAM, "ronda-ingestao")["pending"]


def test_grava_reconhece_e_apaga_da_stream(banco, redis_cliente):
    FilaIngestao(redis_cliente).publicar("demo", "wazuh", [wazuh(), suricata(), fastlog()])
    worker = novo_worker(redis_cliente, GravarEventos(banco))

    stats = worker.processar_lote()

    assert stats.lidas == 3
    assert stats.resultados == {"gravado": 2, "ignorado": 1}  # a cópia do fast.log é ignorada
    assert {e.origem for e in eventos_do_demo(banco)} == {"wazuh", "suricata"}
    assert pendentes(redis_cliente) == 0
    assert redis_cliente.xlen(STREAM) == 0  # reconhecida e apagada


def test_a_mesma_mensagem_duas_vezes_nao_duplica(banco, redis_cliente):
    fila = FilaIngestao(redis_cliente)
    fila.publicar("demo", "wazuh", [wazuh()])
    fila.publicar("demo", "wazuh", [wazuh()])  # reentrega pela integração ou pelo replay
    stats = novo_worker(redis_cliente, GravarEventos(banco)).processar_lote()
    assert stats.resultados == {"gravado": 1, "duplicado": 1}
    assert len(eventos_do_demo(banco)) == 1


def test_alerta_invalido_vai_para_a_stream_de_erro_sem_travar(banco, redis_cliente):
    fila = FilaIngestao(redis_cliente)
    fila.publicar("demo", "wazuh", [{"sem": "rule"}, wazuh()])
    redis_cliente.xadd(STREAM, {"tenant": "demo", "origem": "wazuh", "alerta": "{quebrado"})
    redis_cliente.xadd(STREAM, {"tenant": "demo", "origem": "splunk", "alerta": "{}"})

    stats = novo_worker(redis_cliente, GravarEventos(banco)).processar_lote()

    assert stats.erros == 3 and stats.resultados == {"gravado": 1}
    motivos = [campos["motivo"] for _, campos in redis_cliente.xrange(STREAM_ERROS)]
    assert any("rule.id" in m for m in motivos)
    assert any("não é JSON" in m for m in motivos)
    assert any("origem desconhecida" in m for m in motivos)
    assert pendentes(redis_cliente) == 0


def test_mensagem_de_consumidor_que_caiu_e_retomada_por_outro(banco, redis_cliente):
    FilaIngestao(redis_cliente).publicar("demo", "wazuh", [wazuh()])
    worker_a = novo_worker(redis_cliente, GravarEventos(banco), consumidor="a")
    # "a" lê e morre antes de processar: a mensagem fica pendente com ele.
    redis_cliente.xreadgroup("ronda-ingestao", "a", {STREAM: ">"}, count=10)
    assert pendentes(redis_cliente) == 1

    worker_b = novo_worker(redis_cliente, GravarEventos(banco), consumidor="b", ocioso_ms=0)
    stats = worker_b.processar_lote(bloquear=False)

    assert stats.retomadas == 1 and stats.resultados == {"gravado": 1}
    assert pendentes(redis_cliente) == 0
    assert len(eventos_do_demo(banco)) == 1
    assert worker_a.processar_lote(bloquear=False).lidas == 0


def test_falha_transitoria_fica_pendente_e_depois_de_n_entregas_vai_para_o_erro(redis_cliente):
    tentativas = []

    def banco_fora(tenant, origem, alerta):
        tentativas.append(alerta["id"])
        raise ConnectionError("banco fora do ar")

    FilaIngestao(redis_cliente).publicar("demo", "wazuh", [wazuh()])
    worker = novo_worker(redis_cliente, banco_fora, ocioso_ms=0, max_entregas=3)

    primeira = worker.processar_lote(bloquear=False)
    assert primeira.adiadas == 1 and pendentes(redis_cliente) == 1
    worker.processar_lote(bloquear=False)
    terceira = worker.processar_lote(bloquear=False)

    assert len(tentativas) == 3
    assert terceira.erros == 1 and pendentes(redis_cliente) == 0
    [(_, campos)] = redis_cliente.xrange(STREAM_ERROS)
    assert "falhou 3 vezes" in campos["motivo"]
    assert json.loads(campos["alerta"])["id"] == "1685715378.241"


def test_depois_do_lote_so_roda_quando_houve_mensagem(redis_cliente):
    chamadas = []
    worker = novo_worker(
        redis_cliente, lambda *a: Resultado.gravado, depois_do_lote=lambda: chamadas.append(1)
    )
    worker.processar_lote(bloquear=False)
    FilaIngestao(redis_cliente).publicar("demo", "wazuh", [wazuh()])
    worker.processar_lote(bloquear=False)
    assert chamadas == [1]


@pytest.mark.parametrize("lote", [1, 7])
def test_lote_limita_quantas_mensagens_por_vez(redis_cliente, lote):
    FilaIngestao(redis_cliente).publicar("demo", "wazuh", [wazuh(id=str(i)) for i in range(10)])
    worker = novo_worker(redis_cliente, lambda *a: Resultado.gravado, lote=lote)
    assert worker.processar_lote(bloquear=False).lidas == lote
