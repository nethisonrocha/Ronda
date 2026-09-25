"""Serviços reais (testcontainers) para os testes de integração.

Um PostgreSQL 16 e um Redis 7 por sessão de testes. As migrations rodam como dono (`ronda`,
superusuário da imagem) e a aplicação roda como `ronda_app`, sem privilégios e sujeito à RLS,
igual ao ambiente de desenvolvimento. Sem Docker, os testes são pulados.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import redis
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from ronda.storage.database import BancoDeDados
from tests.conftest import RAIZ

TENANTS = {"demo": "Demonstração", "acme": "Acme"}
TABELAS = "tokens_ingestao, auditoria, notificacoes, decisoes, eventos, incidentes, tenants"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    aqui = Path(__file__).parent
    for item in items:
        if aqui in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integracao)


def _docker_disponivel() -> bool:
    try:
        import docker

        return bool(docker.from_env().ping())
    except Exception:
        return False


@dataclass(frozen=True)
class Esquema:
    url_dono: str
    url_app: str

    def url_do_banco(self, banco: str) -> str:
        base, _ = self.url_dono.rsplit("/", 1)
        return f"{base}/{banco}"


def aplicar_migracoes(url: str, revisao: str = "head") -> None:
    configuracao = Config(str(RAIZ / "alembic.ini"))
    configuracao.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(configuracao, revisao)


def reverter_migracoes(url: str, revisao: str = "base") -> None:
    configuracao = Config(str(RAIZ / "alembic.ini"))
    configuracao.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(configuracao, revisao)


def conceder_ao_app(engine_dono: Engine) -> None:
    with engine_dono.begin() as conexao:
        conexao.execute(text("GRANT USAGE ON SCHEMA public TO ronda_app"))
        conexao.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ronda_app")
        )
        conexao.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ronda_app"))


@pytest.fixture(scope="session")
def esquema() -> Iterator[Esquema]:
    if not _docker_disponivel():
        pytest.skip("Docker indisponível: testes de integração pulados")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(
        "postgres:16-alpine", username="ronda", password="ronda", dbname="ronda", driver="psycopg"
    ) as postgres:
        url_dono = postgres.get_connection_url()
        aplicar_migracoes(url_dono)
        senha_app = secrets.token_hex(16)
        engine = create_engine(url_dono)
        with engine.begin() as conexao:
            conexao.execute(text(f"CREATE ROLE ronda_app LOGIN PASSWORD '{senha_app}' NOBYPASSRLS"))
        conceder_ao_app(engine)
        engine.dispose()
        url_app = url_dono.replace("ronda:ronda@", f"ronda_app:{senha_app}@", 1)
        yield Esquema(url_dono=url_dono, url_app=url_app)


@pytest.fixture(scope="session")
def dono(esquema: Esquema) -> Iterator[Engine]:
    """Conexão do dono (superusuário): ignora a RLS. Só para preparar e inspecionar."""
    engine = create_engine(esquema.url_dono)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def banco(esquema: Esquema) -> Iterator[BancoDeDados]:
    """Banco da aplicação, como ronda_app."""
    banco = BancoDeDados(esquema.url_app)
    yield banco
    banco.fechar()


@pytest.fixture(autouse=True)
def tenants_limpos(dono: Engine) -> Iterator[None]:
    """Cada teste começa com as tabelas vazias e os tenants demo e acme criados."""
    with dono.begin() as conexao:
        conexao.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))
        for tenant, nome in TENANTS.items():
            conexao.execute(
                text("INSERT INTO tenants (id, nome) VALUES (:id, :nome)"),
                {"id": tenant, "nome": nome},
            )
    yield


@pytest.fixture(scope="session")
def redis_url(esquema: Esquema) -> Iterator[str]:
    """Redis 7 real, um container por sessão (depende do esquema só para pular sem Docker)."""
    from testcontainers.community.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        porta = container.get_exposed_port(6379)
        yield f"redis://{host}:{porta}/0"


@pytest.fixture
def redis_cliente(redis_url: str) -> Iterator[redis.Redis]:
    cliente = redis.Redis.from_url(redis_url, decode_responses=True)
    cliente.flushdb()
    yield cliente
    cliente.close()
