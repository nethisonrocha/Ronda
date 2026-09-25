from datetime import UTC, datetime

from sqlalchemy import text

from ronda.storage.repositories import PREFIXO_TOKEN, RepositorioTokens, hash_do_token


def test_token_so_existe_em_claro_na_criacao(banco, dono):
    with banco.sessao("demo") as sessao:
        token, registro = RepositorioTokens(sessao).criar("wazuh-vps")
    assert token.startswith(PREFIXO_TOKEN) and len(token) > 40
    with dono.connect() as conexao:
        guardado = conexao.execute(text("SELECT hash FROM tokens_ingestao")).scalar_one()
    assert guardado == hash_do_token(token) and token not in guardado
    assert registro.nome == "wazuh-vps" and registro.revogado_em is None


def test_token_identifica_o_tenant_e_revogado_deixa_de_valer(banco):
    with banco.sessao("demo") as sessao:
        token, registro = RepositorioTokens(sessao).criar("a")
    with banco.sessao("acme") as sessao:
        token_acme, _ = RepositorioTokens(sessao).criar("b")

    assert banco.tenant_do_token(token) == "demo"
    assert banco.tenant_do_token(token_acme) == "acme"
    assert banco.tenant_do_token("rnd_inventado") is None

    with banco.sessao("demo") as sessao:
        assert RepositorioTokens(sessao).revogar(registro.id, datetime.now(UTC)) is True
        assert RepositorioTokens(sessao).revogar(registro.id, datetime.now(UTC)) is False
    assert banco.tenant_do_token(token) is None


def test_tokens_de_um_tenant_nao_aparecem_no_outro(banco):
    with banco.sessao("demo") as sessao:
        RepositorioTokens(sessao).criar("do-demo")
    with banco.sessao("acme") as sessao:
        assert RepositorioTokens(sessao).listar() == []
        assert sessao.execute(text("SELECT count(*) FROM tokens_ingestao")).scalar() == 0
