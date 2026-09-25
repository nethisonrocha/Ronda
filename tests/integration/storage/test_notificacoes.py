from datetime import UTC, datetime, timedelta

import pytest

from ronda.domain.notification import EstadoNotificacao, ModoNotificacao, Notificacao
from ronda.domain.priority import Prioridade
from ronda.storage.repositories import RepositorioIncidentes, RepositorioNotificacoes

AGORA = datetime(2026, 9, 25, 14, 10, tzinfo=UTC)


@pytest.fixture
def notificacao(banco, incidente):
    """Fábrica de notificações de um incidente já gravado no tenant demo."""
    i = incidente()
    with banco.sessao("demo") as sessao:
        RepositorioIncidentes(sessao).abrir(i)

    def fabricar(**campos) -> Notificacao:
        padrao = {
            "tenant_id": "demo",
            "incidente_id": i.id,
            "canal": "telegram",
            "destino": "123456789",
            "prioridade": Prioridade.P1,
            "modo": ModoNotificacao.imediata,
            "criada_em": AGORA,
        }
        return Notificacao.model_validate(padrao | campos)

    return fabricar


def test_notificacao_volta_igual(banco, notificacao):
    original = notificacao(estado=EstadoNotificacao.suprimida, motivo="silêncio por origem")
    with banco.sessao("demo") as sessao:
        RepositorioNotificacoes(sessao).registrar(original)
    with banco.sessao("demo") as sessao:
        assert RepositorioNotificacoes(sessao).obter(original.id) == original


def test_dois_workers_nunca_reservam_a_mesma_notificacao(banco, notificacao):
    pendentes = [notificacao(criada_em=AGORA + timedelta(seconds=s)) for s in range(3)]
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioNotificacoes(sessao)
        for n in pendentes:
            repositorio.registrar(n)
        repositorio.registrar(notificacao(estado=EstadoNotificacao.enviada))

    with banco.sessao("demo") as sessao_a:
        reservadas_a = RepositorioNotificacoes(sessao_a).reservar_pendentes(limite=2)
        with banco.sessao("demo") as sessao_b:  # outra conexão, com a primeira ainda aberta
            reservadas_b = RepositorioNotificacoes(sessao_b).reservar_pendentes(limite=10)

    assert [n.id for n in reservadas_a] == [pendentes[0].id, pendentes[1].id]  # mais antigas
    assert [n.id for n in reservadas_b] == [pendentes[2].id]


def test_envio_registra_id_externo_e_horario(banco, notificacao):
    n = notificacao()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioNotificacoes(sessao)
        repositorio.registrar(n)
        repositorio.marcar_enviada(n.id, id_externo="msg-42", quando=AGORA)
        enviada = repositorio.obter(n.id)
        assert repositorio.reservar_pendentes() == []

    assert enviada.estado is EstadoNotificacao.enviada
    assert (enviada.id_externo, enviada.enviada_em) == ("msg-42", AGORA)


def test_falha_volta_para_a_fila_ate_esgotar_as_tentativas(banco, notificacao):
    n = notificacao()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioNotificacoes(sessao)
        repositorio.registrar(n)
        estados = [
            repositorio.marcar_falha(n.id, f"timeout {i}", max_tentativas=3) for i in range(3)
        ]
        with pytest.raises(LookupError):
            repositorio.marcar_falha(notificacao().id, "x")

    assert [(e.estado.value, e.tentativas) for e in estados] == [
        ("pendente", 1),
        ("pendente", 2),
        ("falhou", 3),
    ]
    assert estados[-1].motivo == "timeout 2"


def test_so_o_primeiro_reconhecimento_vale(banco, notificacao):
    n = notificacao()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioNotificacoes(sessao)
        repositorio.registrar(n)
        assert repositorio.reconhecer(n.id, "telegram:ana", AGORA) is True
        assert repositorio.reconhecer(n.id, "telegram:beto", AGORA + timedelta(minutes=1)) is False
        lida = repositorio.obter(n.id)
        do_incidente = repositorio.do_incidente(n.incidente_id)

    assert (lida.reconhecida_por, lida.reconhecida_em) == ("telegram:ana", AGORA)
    assert [x.id for x in do_incidente] == [n.id]
