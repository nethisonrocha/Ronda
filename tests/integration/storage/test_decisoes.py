from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ronda.domain.incident import Contexto
from ronda.governance.engine import Motor
from ronda.storage.repositories import (
    RepositorioDecisoes,
    RepositorioEventos,
    RepositorioIncidentes,
)

PAGAMENTOS = "10.0.1.5"


def test_decisao_do_motor_volta_igual_com_o_rastro(banco, politica_demo, evento):
    e = evento(ip_destino=PAGAMENTOS, categoria="forca_bruta")
    decisao = Motor(politica_demo).avaliar(e, Contexto(recorrencia_24h=9, confirmado=True))
    with banco.sessao("demo") as sessao:
        RepositorioEventos(sessao).registrar(e)
        registrada = RepositorioDecisoes(sessao).registrar(decisao, evento_id=e.id)

    with banco.sessao("demo") as sessao:
        lida = RepositorioDecisoes(sessao).obter(registrada.id)

    assert lida.decisao == decisao
    assert lida.decisao.rastro.resumo == decisao.rastro.resumo
    assert "urgência já em alta, sem efeito" in lida.decisao.rastro.resumo
    assert lida.evento_id == e.id and lida.incidente_id is None
    assert lida.decidido_em == registrada.decidido_em


def test_decisao_com_prioridade_base_e_sem_prazo(banco, politica_demo, evento):
    e = evento(categoria="benigno")
    decisao = Motor(politica_demo).avaliar(e)
    with banco.sessao("demo") as sessao:
        RepositorioEventos(sessao).registrar(e)
        lida = RepositorioDecisoes(sessao).registrar(decisao, evento_id=e.id)
    assert lida.decisao.resposta is None
    assert lida.decisao == decisao


def test_historico_do_incidente_em_ordem(banco, politica_demo, evento, incidente):
    i = incidente()
    motor = Motor(politica_demo)
    primeira = motor.avaliar(evento(ip_destino=PAGAMENTOS, categoria="forca_bruta"))
    segunda = motor.avaliar(
        evento(ip_destino=PAGAMENTOS, categoria="forca_bruta"), Contexto(recorrencia_24h=5)
    )
    with banco.sessao("demo") as sessao:
        RepositorioIncidentes(sessao).abrir(i)
        repositorio = RepositorioDecisoes(sessao)
        repositorio.registrar(primeira, incidente_id=i.id)
    with banco.sessao("demo") as sessao:  # transação posterior: decidido_em maior
        RepositorioDecisoes(sessao).registrar(segunda, incidente_id=i.id)

    with banco.sessao("demo") as sessao:
        repositorio = RepositorioDecisoes(sessao)
        historico = repositorio.do_incidente(i.id)
        ultima = repositorio.ultima_do_incidente(i.id)

    assert [d.decisao.prioridade.value for d in historico] == ["P3", "P2"]
    assert ultima.decisao == segunda


def test_decisao_precisa_de_evento_ou_incidente(banco, politica_demo, evento):
    with (
        banco.sessao("demo") as sessao,
        pytest.raises(ValueError, match="evento ou de um incidente"),
    ):
        RepositorioDecisoes(sessao).registrar(Motor(politica_demo).avaliar(evento()))


@pytest.mark.parametrize(
    "comando", ["UPDATE decisoes SET resumo = 'adulterado'", "DELETE FROM decisoes"]
)
def test_decisao_e_somente_insercao(banco, dono, politica_demo, evento, comando):
    e = evento()
    with banco.sessao("demo") as sessao:
        RepositorioEventos(sessao).registrar(e)
        RepositorioDecisoes(sessao).registrar(
            Motor(politica_demo).avaliar(e), evento_id=e.id, decisao_id=uuid4()
        )

    with pytest.raises(DBAPIError, match="somente inserção"), banco.sessao("demo") as sessao:
        sessao.execute(text(comando))
    # Nem o dono (superusuário) escapa do trigger.
    with pytest.raises(DBAPIError, match="somente inserção"), dono.begin() as conexao:
        conexao.execute(text(comando))
