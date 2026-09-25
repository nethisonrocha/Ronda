from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from ronda.storage.models import TABELAS_DE_TENANT, TABELAS_RLS_SEM_FORCE, Base
from tests.integration.conftest import aplicar_migracoes, reverter_migracoes


def test_modelos_e_migration_descrevem_o_mesmo_esquema(dono):
    with dono.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert diferencas == []


def test_rls_ligada_e_forcada_em_todas_as_tabelas(dono):
    with dono.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:tabelas)"
            ),
            {"tabelas": ["tenants", *TABELAS_DE_TENANT]},
        ).all()
        politicas = conexao.execute(
            text("SELECT tablename FROM pg_policies WHERE policyname = 'isolamento_tenant'")
        ).scalars()
        assert set(politicas) == {"tenants", *TABELAS_DE_TENANT}
    assert len(linhas) == 1 + len(TABELAS_DE_TENANT)
    for tabela, ligada, forcada in linhas:
        assert ligada, tabela
        # tokens_ingestao é a exceção documentada: a função SECURITY DEFINER precisa ler.
        assert forcada == (tabela not in TABELAS_RLS_SEM_FORCE), tabela


def test_downgrade_ate_a_base_e_upgrade_de_novo(dono, esquema):
    with dono.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text("DROP DATABASE IF EXISTS ronda_migracoes"))
        conexao.execute(text("CREATE DATABASE ronda_migracoes"))
    url = esquema.url_do_banco("ronda_migracoes")
    engine = create_engine(url)
    try:
        aplicar_migracoes(url)
        assert set(inspect(engine).get_table_names()) >= {"tenants", *TABELAS_DE_TENANT}

        reverter_migracoes(url)
        inspect(engine).clear_cache()
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        with engine.connect() as conexao:
            funcao = conexao.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'ronda_somente_insercao'")
            ).scalar()
        assert funcao == 0

        aplicar_migracoes(url)
        inspect(engine).clear_cache()
        assert set(inspect(engine).get_table_names()) >= {"tenants", *TABELAS_DE_TENANT}
    finally:
        engine.dispose()
        with dono.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
            conexao.execute(text("DROP DATABASE IF EXISTS ronda_migracoes"))
