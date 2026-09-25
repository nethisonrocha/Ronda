from datetime import timedelta

import pytest

from ronda.domain.incident import Contexto, EstadoIncidente
from ronda.domain.priority import Prioridade
from ronda.storage.repositories import (
    IncidenteAtivoExistente,
    RepositorioEventos,
    RepositorioIncidentes,
)


def test_incidente_volta_igual(banco, incidente):
    original = incidente(
        prioridade=Prioridade.P2, contexto=Contexto(recorrencia_24h=7, confirmado=True)
    )
    with banco.sessao("demo") as sessao:
        RepositorioIncidentes(sessao).abrir(original)
    with banco.sessao("demo") as sessao:
        assert RepositorioIncidentes(sessao).obter(original.id) == original


def test_ativo_por_chave_de_correlacao(banco, incidente):
    aberto = incidente()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioIncidentes(sessao)
        repositorio.abrir(aberto)
        achado = repositorio.ativo_por_chave(
            "wazuh", "negacao_servico", "servidor-pagamentos", bloquear=True
        )
        assert achado == aberto
        assert repositorio.ativo_por_chave("wazuh", "negacao_servico", "outro-ativo") is None
        assert repositorio.ativo_por_chave(
            "suricata", "negacao_servico", "servidor-pagamentos"
        ) is (None)


def test_um_so_incidente_ativo_por_chave_e_a_sessao_continua_valida(banco, incidente):
    primeiro = incidente()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioIncidentes(sessao)
        repositorio.abrir(primeiro)
        with pytest.raises(IncidenteAtivoExistente):
            repositorio.abrir(incidente())
        # O savepoint desfez só a tentativa; o resto da transação segue.
        repositorio.abrir(incidente(ativo="ambiente-testes"))

    with banco.sessao("demo") as sessao:
        assert len(RepositorioIncidentes(sessao).listar()) == 2


def test_resolvido_libera_a_chave_para_um_novo_incidente(banco, incidente):
    antigo = incidente()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioIncidentes(sessao)
        repositorio.abrir(antigo)
        assert repositorio.resolver(antigo.id, antigo.aberto_em + timedelta(hours=1))
        novo = repositorio.abrir(incidente())
        assert (
            repositorio.ativo_por_chave("wazuh", "negacao_servico", "servidor-pagamentos").id
            == novo.id
        )


def test_vincular_evento_conta_e_atualiza_o_horario(banco, incidente, evento):
    aberto = incidente()
    depois = evento(ocorrido_em=aberto.aberto_em + timedelta(minutes=5))
    antes = evento(ocorrido_em=aberto.aberto_em - timedelta(minutes=5))
    with banco.sessao("demo") as sessao:
        eventos, incidentes = RepositorioEventos(sessao), RepositorioIncidentes(sessao)
        incidentes.abrir(aberto)
        eventos.registrar(depois)
        eventos.registrar(antes)

        assert incidentes.vincular_evento(aberto.id, depois.id) is True
        assert incidentes.vincular_evento(aberto.id, antes.id) is True
        assert incidentes.vincular_evento(aberto.id, depois.id) is False  # idempotente

        atualizado = incidentes.obter(aberto.id)
        assert atualizado.total_eventos == 2
        assert atualizado.atualizado_em == depois.ocorrido_em  # o mais recente, nunca volta
        assert eventos.incidente_de(depois.id) == aberto.id
        assert [e.id for e in eventos.do_incidente(aberto.id)] == [antes.id, depois.id]


def test_evento_nao_muda_de_incidente_nem_existe_fora_do_tenant(banco, incidente, evento):
    um, outro = incidente(), incidente(ativo="ambiente-testes")
    e = evento()
    with banco.sessao("demo") as sessao:
        incidentes = RepositorioIncidentes(sessao)
        incidentes.abrir(um)
        incidentes.abrir(outro)
        RepositorioEventos(sessao).registrar(e)
        incidentes.vincular_evento(um.id, e.id)
        with pytest.raises(ValueError, match="já pertence"):
            incidentes.vincular_evento(outro.id, e.id)

    with banco.sessao("acme") as sessao, pytest.raises(LookupError):
        RepositorioIncidentes(sessao).vincular_evento(um.id, e.id)


def test_ciclo_aberto_reconhecido_resolvido(banco, incidente):
    i = incidente()
    quando = i.aberto_em + timedelta(minutes=12)
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioIncidentes(sessao)
        repositorio.abrir(i)
        assert repositorio.reconhecer(i.id, quando) is True
        assert repositorio.reconhecer(i.id, quando) is False  # só a partir de aberto
        assert repositorio.resolver(i.id, quando + timedelta(hours=1)) is True
        assert repositorio.resolver(i.id, quando + timedelta(hours=2)) is False
        final = repositorio.obter(i.id)

    assert final.estado is EstadoIncidente.resolvido
    assert final.reconhecido_em - final.aberto_em == timedelta(minutes=12)
    assert final.resolvido_em == quando + timedelta(hours=1)


def test_atualizar_prioridade_e_contexto(banco, incidente):
    i = incidente()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioIncidentes(sessao)
        repositorio.abrir(i)
        repositorio.atualizar_prioridade(i.id, Prioridade.P1, Contexto(recorrencia_24h=5))
        atualizado = repositorio.obter(i.id)
        with pytest.raises(LookupError):
            repositorio.atualizar_prioridade(incidente().id, Prioridade.P1)

    assert atualizado.prioridade is Prioridade.P1
    assert atualizado.contexto.recorrencia_24h == 5


def test_listar_mais_graves_primeiro(banco, incidente):
    base = incidente().aberto_em
    casos = [
        incidente(ativo="a", prioridade=Prioridade.P3, atualizado_em=base),
        incidente(ativo="b", prioridade=Prioridade.P1, atualizado_em=base),
        incidente(ativo="c", prioridade=None, atualizado_em=base),
        incidente(ativo="d", prioridade=Prioridade.P1, atualizado_em=base + timedelta(hours=1)),
    ]
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioIncidentes(sessao)
        for caso in casos:
            repositorio.abrir(caso)
        repositorio.resolver(casos[0].id, base + timedelta(hours=2))

        ordem = [i.ativo for i in repositorio.listar()]
        abertos = [i.ativo for i in repositorio.listar(estado=EstadoIncidente.aberto)]
        p1 = [i.ativo for i in repositorio.listar(prioridade=Prioridade.P1)]

    assert ordem == ["d", "b", "a", "c"]
    assert abertos == ["d", "b", "c"]
    assert p1 == ["d", "b"]
