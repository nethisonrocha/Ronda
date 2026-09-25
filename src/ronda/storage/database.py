"""Conexão com o PostgreSQL e sessões com o tenant definido.

Toda operação de dados acontece dentro de `BancoDeDados.sessao(tenant_id)`: uma transação que
começa com `set_config('app.tenant_id', tenant_id, true)`. O `true` restringe o valor à
transação, então ele nunca vaza para a próxima transação da mesma conexão do pool. As
políticas de RLS da migration leem esse valor; sem ele, nada é visível nem gravável.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ronda.config import Configuracao, obter_configuracao
from ronda.domain.event import TENANT_PATTERN


class SessaoSemTenant(RuntimeError):
    """Um repositório recebeu uma sessão aberta fora de `BancoDeDados.sessao`."""


class BancoDeDados:
    def __init__(self, url: str, **opcoes_engine: object) -> None:
        self.engine: Engine = create_engine(url, pool_pre_ping=True, **opcoes_engine)
        self._fabrica = sessionmaker(self.engine, expire_on_commit=False)

    @classmethod
    def da_configuracao(cls, configuracao: Configuracao | None = None) -> BancoDeDados:
        configuracao = configuracao or obter_configuracao()
        if configuracao.url_banco is None:
            raise RuntimeError("defina RONDA_DATABASE_URL (veja .env.example)")
        return cls(str(configuracao.url_banco))

    @contextmanager
    def sessao(self, tenant_id: str) -> Iterator[Session]:
        """Transação de um tenant: confirma ao sair, desfaz se houver exceção."""
        if not re.fullmatch(TENANT_PATTERN, tenant_id):
            raise ValueError(f"tenant inválido: {tenant_id!r}")
        with self._fabrica() as sessao, sessao.begin():
            sessao.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id}
            )
            sessao.info["tenant_id"] = tenant_id
            yield sessao

    def fechar(self) -> None:
        self.engine.dispose()


def tenant_da_sessao(sessao: Session) -> str:
    try:
        return sessao.info["tenant_id"]
    except KeyError:
        raise SessaoSemTenant("abra a sessão com BancoDeDados.sessao(tenant_id)") from None
