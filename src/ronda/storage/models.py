"""Modelos ORM (SQLAlchemy 2) das tabelas do Ronda.

Regras que valem para todas as tabelas:

- **tenant_id em todas**, e chave primária composta `(tenant_id, id)`. As chaves estrangeiras
  entre tabelas de tenant também são compostas: uma decisão do tenant A não consegue apontar
  para um evento do tenant B, nem por engano.
- **Row-Level Security** por `app.tenant_id`, criada na migration (não aparece aqui).
- `decisoes` e `auditoria` são somente inserção (trigger na migration).

Estes modelos e a migration precisam descrever o mesmo esquema; o teste de migrations compara
os dois.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Interval,
    MetaData,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime

CONVENCAO_NOMES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PRIORIDADES = "'P1', 'P2', 'P3', 'P4'"
NIVEIS_F = "'baixa', 'media', 'alta'"
NIVEIS_M = "'baixo', 'medio', 'alto'"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)
    # Atributo de classe mutável exigido pelo SQLAlchemy.
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        timedelta: Interval(),
        dict[str, Any]: JSONB,
        list[dict[str, Any]]: JSONB,
        IPv4Address | IPv6Address: INET,
    }


def _tenant() -> Mapped[str]:
    return mapped_column(String(63), ForeignKey("tenants.id"), primary_key=True)


def _agora() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


class TenantModel(Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("id ~ '^[a-z0-9][a-z0-9-]{0,62}$'", name="id_valido"),)

    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = _agora()


class EventoModel(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "incidente_id"], ["incidentes.tenant_id", "incidentes.id"]
        ),
        # Idempotência da ingestão: a mesma mensagem entregue duas vezes não vira dois eventos.
        Index(
            "uq_eventos_origem_id_origem",
            "tenant_id",
            "origem",
            "id_origem",
            unique=True,
            postgresql_where=text("id_origem IS NOT NULL"),
        ),
        Index("ix_eventos_tenant_id_ocorrido_em", "tenant_id", "ocorrido_em"),
        Index("ix_eventos_tenant_id_incidente_id", "tenant_id", "incidente_id"),
    )

    tenant_id: Mapped[str] = _tenant()
    id: Mapped[UUID] = mapped_column(primary_key=True)
    id_origem: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(Text)
    severidade_origem: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    ip_origem: Mapped[IPv4Address | IPv6Address | None]
    ip_destino: Mapped[IPv4Address | IPv6Address | None]
    ativo: Mapped[str | None] = mapped_column(Text)
    ocorrido_em: Mapped[datetime]
    recebido_em: Mapped[datetime] = _agora()
    evidencias: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    bruto: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    incidente_id: Mapped[UUID | None]


class IncidenteModel(Base):
    __tablename__ = "incidentes"
    __table_args__ = (
        CheckConstraint("estado IN ('aberto', 'reconhecido', 'resolvido')", name="estado"),
        CheckConstraint(f"prioridade IN ({PRIORIDADES})", name="prioridade"),
        CheckConstraint("total_eventos >= 0", name="total_eventos"),
        # No máximo um incidente ativo por chave de correlação.
        Index(
            "uq_incidentes_ativo_por_chave",
            "tenant_id",
            "chave_correlacao",
            unique=True,
            postgresql_where=text("estado <> 'resolvido'"),
        ),
        Index("ix_incidentes_tenant_id_estado_prioridade", "tenant_id", "estado", "prioridade"),
    )

    tenant_id: Mapped[str] = _tenant()
    id: Mapped[UUID] = mapped_column(primary_key=True)
    origem: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(Text)
    ativo: Mapped[str | None] = mapped_column(Text)
    chave_correlacao: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, server_default=text("'aberto'"))
    prioridade: Mapped[str | None] = mapped_column(Text)
    total_eventos: Mapped[int] = mapped_column(server_default=text("0"))
    contexto: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    aberto_em: Mapped[datetime]
    atualizado_em: Mapped[datetime]
    reconhecido_em: Mapped[datetime | None]
    resolvido_em: Mapped[datetime | None]


class DecisaoModel(Base):
    __tablename__ = "decisoes"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "evento_id"], ["eventos.tenant_id", "eventos.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "incidente_id"], ["incidentes.tenant_id", "incidentes.id"]
        ),
        CheckConstraint(
            "evento_id IS NOT NULL OR incidente_id IS NOT NULL", name="evento_ou_incidente"
        ),
        CheckConstraint(f"prioridade IN ({PRIORIDADES})", name="prioridade"),
        CheckConstraint(f"criticidade IN ({NIVEIS_F})", name="criticidade"),
        CheckConstraint(f"impacto IN ({NIVEIS_M})", name="impacto"),
        CheckConstraint(f"urgencia IN ({NIVEIS_F})", name="urgencia"),
        CheckConstraint("jsonb_typeof(rastro) = 'array'", name="rastro_lista"),
        Index(
            "ix_decisoes_tenant_id_incidente_id_decidido_em",
            "tenant_id",
            "incidente_id",
            "decidido_em",
        ),
        Index("ix_decisoes_tenant_id_evento_id", "tenant_id", "evento_id"),
    )

    tenant_id: Mapped[str] = _tenant()
    id: Mapped[UUID] = mapped_column(primary_key=True)
    evento_id: Mapped[UUID | None]
    incidente_id: Mapped[UUID | None]
    prioridade: Mapped[str] = mapped_column(Text)
    impacto: Mapped[str | None] = mapped_column(Text)
    urgencia: Mapped[str | None] = mapped_column(Text)
    criticidade: Mapped[str] = mapped_column(Text)
    ativo: Mapped[str | None] = mapped_column(Text)
    resposta: Mapped[timedelta | None]
    politica_versao: Mapped[int]
    prioridade_base: Mapped[bool]
    rastro: Mapped[list[dict[str, Any]]]
    resumo: Mapped[str] = mapped_column(Text)
    decidido_em: Mapped[datetime] = _agora()


class NotificacaoModel(Base):
    __tablename__ = "notificacoes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "incidente_id"], ["incidentes.tenant_id", "incidentes.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "decisao_id"], ["decisoes.tenant_id", "decisoes.id"]),
        CheckConstraint(f"prioridade IN ({PRIORIDADES})", name="prioridade"),
        CheckConstraint("modo IN ('imediata', 'agrupada', 'resumo_diario')", name="modo"),
        CheckConstraint("estado IN ('pendente', 'enviada', 'falhou', 'suprimida')", name="estado"),
        CheckConstraint("tentativas >= 0", name="tentativas"),
        Index("ix_notificacoes_tenant_id_estado_criada_em", "tenant_id", "estado", "criada_em"),
        Index("ix_notificacoes_tenant_id_incidente_id", "tenant_id", "incidente_id"),
    )

    tenant_id: Mapped[str] = _tenant()
    id: Mapped[UUID] = mapped_column(primary_key=True)
    incidente_id: Mapped[UUID]
    decisao_id: Mapped[UUID | None]
    canal: Mapped[str] = mapped_column(Text)
    destino: Mapped[str] = mapped_column(Text)
    prioridade: Mapped[str] = mapped_column(Text)
    modo: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, server_default=text("'pendente'"))
    motivo: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(server_default=text("0"))
    id_externo: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = _agora()
    enviada_em: Mapped[datetime | None]
    reconhecida_em: Mapped[datetime | None]
    reconhecida_por: Mapped[str | None] = mapped_column(Text)


class AuditoriaModel(Base):
    __tablename__ = "auditoria"
    __table_args__ = (
        Index("ix_auditoria_tenant_id_ocorrido_em", "tenant_id", "ocorrido_em"),
        Index(
            "ix_auditoria_tenant_id_entidade_entidade_id", "tenant_id", "entidade", "entidade_id"
        ),
    )

    tenant_id: Mapped[str] = _tenant()
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ocorrido_em: Mapped[datetime] = _agora()
    ator: Mapped[str] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text)
    entidade: Mapped[str] = mapped_column(Text)
    entidade_id: Mapped[str | None] = mapped_column(Text)
    dados: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class TokenIngestaoModel(Base):
    """Token de ingestão de um tenant; só o hash (sha256) é guardado.

    Exceção à regra do FORCE: a RLS está ligada, mas não forçada, porque a função
    ``ronda_tenant_do_token`` (SECURITY DEFINER, do dono) precisa achar o tenant pelo hash
    antes de existir um tenant na sessão. O papel da aplicação continua sujeito à RLS.
    """

    __tablename__ = "tokens_ingestao"
    __table_args__ = (Index("uq_tokens_ingestao_hash", "hash", unique=True),)

    tenant_id: Mapped[str] = _tenant()
    id: Mapped[UUID] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = _agora()
    revogado_em: Mapped[datetime | None]


TABELAS_DE_TENANT = (
    "eventos",
    "incidentes",
    "decisoes",
    "notificacoes",
    "auditoria",
    "tokens_ingestao",
)
# Tabelas com RLS ligada, mas sem FORCE (ver TokenIngestaoModel).
TABELAS_RLS_SEM_FORCE = ("tokens_ingestao",)
TABELAS_SOMENTE_INSERCAO = ("decisoes", "auditoria")
