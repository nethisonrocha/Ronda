from datetime import UTC, datetime, timedelta

from ronda.storage.repositories import RepositorioEventos

INICIO = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)


def test_evento_completo_volta_igual(banco, evento):
    original = evento(
        severidade_origem=10,
        ip_origem="203.0.113.7",
        ip_destino="2001:db8::5",
        ativo="servidor-pagamentos",
        evidencias={"regra": 5712, "grupos": ["sshd", "authentication_failed"]},
        bruto={"rule": {"id": "5712", "level": 10}, "agent": {"name": "web01"}},
    )
    with banco.sessao("demo") as sessao:
        assert RepositorioEventos(sessao).registrar(original, id_origem="1685715378.241")

    with banco.sessao("demo") as sessao:
        assert RepositorioEventos(sessao).obter(original.id) == original


def test_severidade_textual_e_ausente_preservam_o_tipo(banco, evento):
    textual, ausente = evento(severidade_origem="alta"), evento()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioEventos(sessao)
        repositorio.registrar(textual)
        repositorio.registrar(ausente)
        assert repositorio.obter(textual.id).severidade_origem == "alta"
        assert repositorio.obter(ausente.id).severidade_origem is None


def test_mesma_mensagem_entregue_duas_vezes_nao_duplica(banco, evento):
    """A fila entrega pelo menos uma vez; o id do alerta na ferramenta segura a duplicata."""
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioEventos(sessao)
        assert repositorio.registrar(evento(), id_origem="abc") is True
        assert repositorio.registrar(evento(), id_origem="abc") is False
        assert repositorio.registrar(evento(origem="suricata"), id_origem="abc") is True
        assert len(repositorio.listar()) == 2


def test_mesmo_id_duas_vezes_nao_duplica(banco, evento):
    e = evento()
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioEventos(sessao)
        assert repositorio.registrar(e) is True
        assert repositorio.registrar(e) is False


def test_mesmo_id_origem_em_tenants_diferentes_e_permitido(banco, evento):
    with banco.sessao("demo") as sessao:
        assert RepositorioEventos(sessao).registrar(evento(), id_origem="abc")
    with banco.sessao("acme") as sessao:
        assert RepositorioEventos(sessao).registrar(evento(tenant_id="acme"), id_origem="abc")


def test_listar_por_periodo_em_ordem(banco, evento):
    eventos = [evento(ocorrido_em=INICIO + timedelta(minutes=m)) for m in (30, 0, 10, 20)]
    with banco.sessao("demo") as sessao:
        repositorio = RepositorioEventos(sessao)
        for e in eventos:
            repositorio.registrar(e)

        todos = repositorio.listar()
        janela = repositorio.listar(
            desde=INICIO + timedelta(minutes=10), ate=INICIO + timedelta(minutes=30)
        )
        primeiros = repositorio.listar(limite=2)

    assert [e.ocorrido_em for e in todos] == sorted(e.ocorrido_em for e in eventos)
    assert [e.ocorrido_em.minute for e in janela] == [10, 20]
    assert [e.ocorrido_em.minute for e in primeiros] == [0, 10]
