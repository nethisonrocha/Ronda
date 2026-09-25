"""Ambiente do Alembic.

Ordem de onde vem a URL do banco:

1. `-x url=...` na linha de comando;
2. `sqlalchemy.url` definida por quem chama (os testes fazem isso);
3. `RONDA_DATABASE_MIGRATION_URL` (config.py / .env), com o papel dono das tabelas.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from ronda.config import obter_configuracao
from ronda.storage.models import Base

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:
    # Sem desligar os loggers já existentes (os do pytest, por exemplo).
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _url() -> str:
    url = context.get_x_argument(as_dictionary=True).get("url") or config.get_main_option(
        "sqlalchemy.url"
    )
    if url:
        return url
    configurada = obter_configuracao().url_banco_migracao
    if configurada is None:
        raise RuntimeError(
            "sem URL de migração: defina RONDA_DATABASE_MIGRATION_URL no .env "
            "ou passe -x url=postgresql+psycopg://..."
        )
    return str(configurada)


def rodar_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def rodar_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conexao:
        context.configure(connection=conexao, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    rodar_offline()
else:
    rodar_online()
