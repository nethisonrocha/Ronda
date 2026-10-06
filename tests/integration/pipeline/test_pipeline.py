from datetime import UTC, datetime, timedelta

import pytest
import yaml

from ronda.domain.incident import EstadoIncidente
from ronda.domain.priority import Prioridade
from ronda.governance.policy import RepositorioPoliticas
from ronda.storage.repositories import (
    RepositorioAuditoria,
    RepositorioDecisoes,
    RepositorioEventos,
    RepositorioIncidentes,
)
from ronda.workers.ingestao import Resultado
from ronda.workers.pipeline import Pipeline
from tests.conftest import POLITICAS_EXEMPLO

T0 = datetime(2022, 1, 21, 10, 0, tzinfo=UTC)
PAGAMENTOS = "10.0.1.5"


def em(minutos):
    return T0 + timedelta(minutes=minutos)


@pytest.fixture
def pipeline(banco):
    return Pipeline(banco, RepositorioPoliticas(POLITICAS_EXEMPLO))


@pytest.fixture
def pipeline_janela_longa(banco, tmp_path):
    """Política demo com janela de 7 dias, para a recorrência poder cair com o incidente aberto."""
    dados = yaml.safe_load((POLITICAS_EXEMPLO / "demo.yaml").read_text(encoding="utf-8"))
    dados["correlacao"] = {"janela": "7d"}
    # O silêncio por origem precisa ser maior que a janela; aqui só a correlação importa.
    dados["notificacao"]["silencio_por_origem"] = "8d"
    (tmp_path / "demo.yaml").write_text(yaml.safe_dump(dados), encoding="utf-8")
    return Pipeline(banco, RepositorioPoliticas(tmp_path))


def forca_bruta(evento, minuto, **campos):
    return evento(categoria="forca_bruta", ip_destino=PAGAMENTOS, ocorrido_em=em(minuto), **campos)


def ler(banco, funcao):
    with banco.sessao("demo") as sessao:
        return funcao(sessao)


def test_eventos_da_mesma_chave_viram_um_incidente_e_a_decisao_so_e_gravada_quando_sobe(
    banco, pipeline, evento
):
    # Força bruta só sobe com 50 falhas em 24 h (decisão A1 de 06/10/2026).
    resultados = [pipeline.processar_evento(forca_bruta(evento, m)) for m in range(51)]

    assert {r.incidente_id for r in resultados} == {resultados[0].incidente_id}
    assert [r.prioridade for r in resultados] == [Prioridade.P3] * 49 + [Prioridade.P2] * 2
    assert [r.decisao_id is not None for r in resultados] == [True] + [False] * 48 + [True, False]

    incidente = ler(banco, lambda s: RepositorioIncidentes(s).obter(resultados[0].incidente_id))
    decisoes = ler(banco, lambda s: RepositorioDecisoes(s).do_incidente(incidente.id))
    assert (incidente.total_eventos, incidente.prioridade) == (51, Prioridade.P2)
    assert incidente.contexto.recorrencia_24h == 51
    assert incidente.chave_correlacao == "wazuh|forca_bruta|servidor-pagamentos"
    assert [d.decisao.prioridade for d in decisoes] == [Prioridade.P3, Prioridade.P2]
    rastro = decisoes[-1].decisao.rastro.resumo
    assert "recorrencia_24h >= 50 (só forca_bruta): urgência sobe para alta" in rastro


def test_depois_da_janela_o_incidente_se_encerra_e_outro_abre(banco, pipeline, evento):
    primeiro = pipeline.processar_evento(forca_bruta(evento, 0))
    pipeline.processar_evento(forca_bruta(evento, 10))
    segundo = pipeline.processar_evento(forca_bruta(evento, 50))  # 40 min depois do último

    assert segundo.novo_incidente and segundo.incidente_id != primeiro.incidente_id
    antigo = ler(banco, lambda s: RepositorioIncidentes(s).obter(primeiro.incidente_id))
    assert antigo.estado is EstadoIncidente.resolvido
    assert antigo.resolvido_em == em(40)  # último evento (10) + janela (30)
    # A recorrência cruza incidentes: o novo já nasce vendo os três eventos da chave.
    novo = ler(banco, lambda s: RepositorioIncidentes(s).obter(segundo.incidente_id))
    assert novo.contexto.recorrencia_24h == 3
    acoes = [e.acao for e in ler(banco, lambda s: RepositorioAuditoria(s).listar())]
    assert "incidente.encerrado_por_inatividade" in acoes


def test_a_mesma_mensagem_de_novo_nao_mexe_em_nada(banco, pipeline, evento):
    e = forca_bruta(evento, 0, id_origem="w-1")
    assert pipeline.processar_evento(e).resultado is Resultado.gravado
    repetido = pipeline.processar_evento(e)
    assert repetido.resultado is Resultado.duplicado and repetido.incidente_id is None
    incidentes = ler(banco, lambda s: RepositorioIncidentes(s).listar())
    assert [i.total_eventos for i in incidentes] == [1]


def test_prioridade_nao_desce_quando_a_recorrencia_cai(banco, pipeline_janela_longa, evento):
    for m in range(50):
        pipeline_janela_longa.processar_evento(forca_bruta(evento, m))  # recorrência 50 → P2
    depois = pipeline_janela_longa.processar_evento(forca_bruta(evento, 25 * 60))  # 25 h depois

    incidente = ler(banco, lambda s: RepositorioIncidentes(s).obter(depois.incidente_id))
    assert incidente.contexto.recorrencia_24h == 1  # os cinquenta saíram da janela de 24 h
    assert incidente.prioridade is Prioridade.P2 and depois.decisao_id is None
    decisoes = ler(banco, lambda s: RepositorioDecisoes(s).do_incidente(incidente.id))
    assert [d.decisao.prioridade for d in decisoes] == [Prioridade.P3, Prioridade.P2]


def test_encerrar_inativos_pela_marca_do_evento_mais_recente(banco, pipeline, evento):
    parado = pipeline.processar_evento(forca_bruta(evento, 0))
    ativo = pipeline.processar_evento(evento(categoria="reconhecimento", ocorrido_em=em(120)))

    assert pipeline.encerrar_inativos() == 1
    incidentes = {i.id: i for i in ler(banco, lambda s: RepositorioIncidentes(s).listar())}
    assert incidentes[parado.incidente_id].estado is EstadoIncidente.resolvido
    assert incidentes[parado.incidente_id].resolvido_em == em(30)
    assert incidentes[ativo.incidente_id].estado is EstadoIncidente.aberto
    assert pipeline.encerrar_inativos() == 0  # idempotente


def test_gancho_do_notificador_roda_a_cada_subida_dentro_da_transacao(banco, evento):
    chamadas = []

    def ao_priorizar(sessao, politica, incidente, reav, registrada):
        chamadas.append((incidente.prioridade, registrada.id, sessao.info["tenant_id"]))

    pipeline = Pipeline(banco, RepositorioPoliticas(POLITICAS_EXEMPLO), ao_priorizar=ao_priorizar)
    for m in range(50):
        pipeline.processar_evento(forca_bruta(evento, m))
    assert [(p, t) for p, _, t in chamadas] == [(Prioridade.P3, "demo"), (Prioridade.P2, "demo")]


def test_chaves_diferentes_nao_se_misturam(banco, pipeline, evento):
    a = pipeline.processar_evento(forca_bruta(evento, 0))
    b = pipeline.processar_evento(
        evento(categoria="forca_bruta", ip_destino="10.0.9.20", ocorrido_em=em(1))
    )
    c = pipeline.processar_evento(
        evento(categoria="negacao_servico", ip_destino=PAGAMENTOS, ocorrido_em=em(2))
    )
    assert len({a.incidente_id, b.incidente_id, c.incidente_id}) == 3
    assert c.prioridade is Prioridade.P1  # DoS no servidor de pagamentos
    eventos = ler(banco, lambda s: RepositorioEventos(s).listar())
    assert len(eventos) == 3


def test_comprometimento_depois_de_ataque_grave_no_mesmo_ativo_vira_p1(banco, pipeline, evento):
    """A5: o sudo sozinho é P2 no expediente (em(240) é sexta, 11:00 em Fortaleza); depois de
    um ataque web P1 no mesmo ativo, o mesmo alerta vira P1: é o passo seguinte do ataque."""
    sozinho = pipeline.processar_evento(
        evento(categoria="comprometimento", ip_destino="10.0.1.6", ocorrido_em=em(240))
    )
    assert sozinho.prioridade is Prioridade.P2

    pipeline.processar_evento(
        evento(categoria="ataque_web", ip_destino=PAGAMENTOS, ocorrido_em=em(300))
    )  # P1 no servidor de pagamentos
    depois = pipeline.processar_evento(
        evento(categoria="comprometimento", ip_destino=PAGAMENTOS, ocorrido_em=em(330))
    )
    assert depois.prioridade is Prioridade.P1
    decisao = ler(banco, lambda s: RepositorioDecisoes(s).obter(depois.decisao_id))
    assert "ataque_previo_no_ativo (só comprometimento): urgência sobe para alta" in (
        decisao.decisao.rastro.resumo
    )
