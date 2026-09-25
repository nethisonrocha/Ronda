"""Isolamento entre tenants: filtro explícito, RLS do banco e chaves compostas."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from ronda.storage.database import BancoDeDados, SessaoSemTenant
from ronda.storage.repositories import (
    OutroTenant,
    RepositorioEventos,
    RepositorioIncidentes,
    RepositorioTenants,
)


def test_evento_de_um_tenant_nao_aparece_no_outro(banco, evento):
    do_demo = evento()
    with banco.sessao("demo") as sessao:
        RepositorioEventos(sessao).registrar(do_demo)

    with banco.sessao("acme") as sessao:
        repositorio = RepositorioEventos(sessao)
        assert repositorio.obter(do_demo.id) is None
        assert repositorio.listar() == []

    with banco.sessao("demo") as sessao:
        assert RepositorioEventos(sessao).obter(do_demo.id) == do_demo


def test_repositorio_recusa_objeto_de_outro_tenant(banco, evento, incidente):
    with banco.sessao("demo") as sessao:
        with pytest.raises(OutroTenant):
            RepositorioEventos(sessao).registrar(evento(tenant_id="acme"))
        with pytest.raises(OutroTenant):
            RepositorioIncidentes(sessao).abrir(incidente(tenant_id="acme"))


def test_rls_recusa_gravar_em_outro_tenant_mesmo_por_sql_direto(banco):
    """Mesmo que o código erre, o banco não deixa a sessão do demo gravar como acme."""
    with pytest.raises(DBAPIError, match="row-level security"), banco.sessao("demo") as sessao:
        sessao.execute(
            text(
                "INSERT INTO eventos (tenant_id, id, origem, categoria, ocorrido_em) "
                "VALUES ('acme', :id, 'wazuh', 'benigno', now())"
            ),
            {"id": uuid4()},
        )


def test_sem_tenant_definido_nada_e_visivel_nem_gravavel(banco, esquema, evento):
    with banco.sessao("demo") as sessao:
        RepositorioEventos(sessao).registrar(evento())

    engine = create_engine(esquema.url_app)
    try:
        with engine.connect() as conexao:
            assert conexao.execute(text("SELECT count(*) FROM eventos")).scalar() == 0
            assert conexao.execute(text("SELECT count(*) FROM tenants")).scalar() == 0
            with pytest.raises(DBAPIError, match="row-level security"):
                conexao.execute(
                    text(
                        "INSERT INTO eventos (tenant_id, id, origem, categoria, ocorrido_em) "
                        "VALUES ('demo', :id, 'wazuh', 'benigno', now())"
                    ),
                    {"id": uuid4()},
                )
    finally:
        engine.dispose()


def test_tenant_so_enxerga_a_propria_linha_em_tenants(banco):
    with banco.sessao("acme") as sessao:
        assert RepositorioTenants(sessao).nome() == "Acme"
        assert sessao.execute(text("SELECT count(*) FROM tenants")).scalar() == 1


def test_tenant_definido_nao_vaza_para_a_proxima_transacao(esquema, evento):
    """set_config(..., true) vale só para a transação: a mesma conexão física, devolvida ao
    pool, chega limpa à transação seguinte."""
    banco = BancoDeDados(esquema.url_app, pool_size=1, max_overflow=0)
    try:
        with banco.sessao("demo") as sessao:
            RepositorioEventos(sessao).registrar(evento())
            fisica = sessao.connection().connection.dbapi_connection
        with banco.engine.connect() as proxima:
            assert proxima.connection.dbapi_connection is fisica  # mesma conexão do pool
            tenant = proxima.execute(text("SELECT current_setting('app.tenant_id', true)"))
            assert tenant.scalar() in (None, "")
            assert proxima.execute(text("SELECT count(*) FROM eventos")).scalar() == 0
    finally:
        banco.fechar()


def test_chave_estrangeira_composta_impede_referencia_entre_tenants(dono, banco, evento):
    """Nem o dono, que ignora a RLS, consegue ligar uma decisão do demo a um evento do acme."""
    do_acme = evento(tenant_id="acme")
    with banco.sessao("acme") as sessao:
        RepositorioEventos(sessao).registrar(do_acme)

    with (
        pytest.raises(IntegrityError, match="fk_decisoes_tenant_id_evento_id_eventos"),
        dono.begin() as conexao,
    ):
        conexao.execute(
            text(
                "INSERT INTO decisoes (tenant_id, id, evento_id, prioridade, criticidade, "
                "politica_versao, prioridade_base, rastro, resumo) VALUES "
                "('demo', :id, :evento, 'P1', 'alta', 1, false, '[]', 'x')"
            ),
            {"id": uuid4(), "evento": do_acme.id},
        )


def test_sessao_com_tenant_invalido_e_recusada(banco):
    with pytest.raises(ValueError, match="tenant inválido"), banco.sessao("../acme"):
        pass


def test_repositorio_exige_sessao_com_tenant(banco):
    with Session(banco.engine) as sessao, pytest.raises(SessaoSemTenant):
        RepositorioEventos(sessao)


def test_garantir_cria_so_o_proprio_tenant_e_e_idempotente(banco, dono):
    with banco.sessao("novo") as sessao:
        repositorio = RepositorioTenants(sessao)
        repositorio.garantir("Novo cliente")
        repositorio.garantir("Nome ignorado na segunda vez")
        assert repositorio.nome() == "Novo cliente"
    with dono.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM tenants")).scalar() == 3


def test_banco_a_partir_da_configuracao(esquema):
    from ronda.config import Configuracao

    with pytest.raises(RuntimeError, match="RONDA_DATABASE_URL"):
        BancoDeDados.da_configuracao(Configuracao(_env_file=None))
    banco = BancoDeDados.da_configuracao(Configuracao(_env_file=None, url_banco=esquema.url_app))
    try:
        with banco.sessao("demo") as sessao:
            assert RepositorioTenants(sessao).nome() == "Demonstração"
    finally:
        banco.fechar()
