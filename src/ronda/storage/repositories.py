"""Repositórios: tradução entre o domínio e as tabelas, sempre dentro do tenant da sessão.

Cada repositório recebe uma sessão aberta por `BancoDeDados.sessao(tenant_id)`. O isolamento
tem duas camadas: toda consulta filtra por `tenant_id` explicitamente, e a RLS do banco recusa
o que escapar. Gravar um objeto de outro tenant é erro antes mesmo de chegar ao banco.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ronda.domain.event import Evento
from ronda.domain.incident import Contexto, EstadoIncidente, Incidente, chave_correlacao
from ronda.domain.notification import EstadoNotificacao, Notificacao
from ronda.domain.priority import Prioridade
from ronda.governance.engine import Decisao
from ronda.governance.trace import Rastro
from ronda.storage.database import tenant_da_sessao
from ronda.storage.models import (
    AuditoriaModel,
    DecisaoModel,
    EventoModel,
    IncidenteModel,
    NotificacaoModel,
    TenantModel,
    TokenIngestaoModel,
)


class OutroTenant(ValueError):
    """Tentativa de gravar um objeto de outro tenant na sessão atual."""


class IncidenteAtivoExistente(ValueError):
    """Já existe um incidente ativo com a mesma chave de correlação."""


def _ip(valor: object) -> IPv4Address | IPv6Address | None:
    # O psycopg devolve inet como endereço ou como interface ("10.0.0.5/32").
    return None if valor is None else ip_address(str(valor).split("/")[0])


class _Repositorio:
    def __init__(self, sessao: Session) -> None:
        self.sessao = sessao
        self.tenant = tenant_da_sessao(sessao)

    def _mesmo_tenant(self, tenant_id: str) -> None:
        if tenant_id != self.tenant:
            raise OutroTenant(f"objeto do tenant {tenant_id!r} numa sessão de {self.tenant!r}")


# --- tenants -----------------------------------------------------------------------------


class RepositorioTenants(_Repositorio):
    """Sob RLS, a sessão só enxerga e só cria o próprio tenant."""

    def garantir(self, nome: str) -> None:
        self.sessao.execute(
            insert(TenantModel).values(id=self.tenant, nome=nome).on_conflict_do_nothing()
        )

    def nome(self) -> str | None:
        return self.sessao.scalar(select(TenantModel.nome).where(TenantModel.id == self.tenant))


# --- eventos -----------------------------------------------------------------------------


class RepositorioEventos(_Repositorio):
    def registrar(self, evento: Evento, id_origem: str | None = None) -> bool:
        """Grava o evento. Devolve False se ele já existia (mesmo id ou mesmo id_origem).

        Com `id_origem` (o id do alerta na ferramenta; por padrão, o do próprio evento), a
        ingestão é idempotente: a mesma mensagem entregue duas vezes não vira dois eventos.
        """
        self._mesmo_tenant(evento.tenant_id)
        id_origem = id_origem or evento.id_origem
        json = evento.model_dump(mode="json", include={"severidade_origem", "evidencias", "bruto"})
        # RETURNING, e não rowcount: pelo ORM, o rowcount de um INSERT não é confiável.
        inserido = self.sessao.execute(
            insert(EventoModel)
            .values(
                tenant_id=evento.tenant_id,
                id=evento.id,
                id_origem=id_origem,
                origem=evento.origem,
                categoria=evento.categoria.value,
                severidade_origem=json["severidade_origem"],
                ip_origem=evento.ip_origem,
                ip_destino=evento.ip_destino,
                ativo=evento.ativo,
                ocorrido_em=evento.ocorrido_em,
                evidencias=json["evidencias"],
                bruto=json["bruto"],
            )
            .on_conflict_do_nothing()
            .returning(EventoModel.id)
        ).scalar_one_or_none()
        return inserido is not None

    def obter(self, evento_id: UUID) -> Evento | None:
        linha = self.sessao.get(EventoModel, (self.tenant, evento_id))
        return None if linha is None else self._para_dominio(linha)

    def incidente_de(self, evento_id: UUID) -> UUID | None:
        return self.sessao.scalar(
            select(EventoModel.incidente_id).where(
                EventoModel.tenant_id == self.tenant, EventoModel.id == evento_id
            )
        )

    def listar(
        self, desde: datetime | None = None, ate: datetime | None = None, limite: int = 100
    ) -> list[Evento]:
        consulta = select(EventoModel).where(EventoModel.tenant_id == self.tenant)
        if desde is not None:
            consulta = consulta.where(EventoModel.ocorrido_em >= desde)
        if ate is not None:
            consulta = consulta.where(EventoModel.ocorrido_em < ate)
        consulta = consulta.order_by(EventoModel.ocorrido_em, EventoModel.id).limit(limite)
        return [self._para_dominio(linha) for linha in self.sessao.scalars(consulta)]

    def do_incidente(self, incidente_id: UUID, limite: int = 100) -> list[Evento]:
        consulta = (
            select(EventoModel)
            .where(EventoModel.tenant_id == self.tenant, EventoModel.incidente_id == incidente_id)
            .order_by(EventoModel.ocorrido_em, EventoModel.id)
            .limit(limite)
        )
        return [self._para_dominio(linha) for linha in self.sessao.scalars(consulta)]

    @staticmethod
    def _para_dominio(linha: EventoModel) -> Evento:
        return Evento(
            id=linha.id,
            tenant_id=linha.tenant_id,
            origem=linha.origem,
            id_origem=linha.id_origem,
            categoria=linha.categoria,
            severidade_origem=linha.severidade_origem,
            ip_origem=_ip(linha.ip_origem),
            ip_destino=_ip(linha.ip_destino),
            ativo=linha.ativo,
            ocorrido_em=linha.ocorrido_em,
            evidencias=linha.evidencias,
            bruto=linha.bruto,
        )


# --- incidentes --------------------------------------------------------------------------


class RepositorioIncidentes(_Repositorio):
    def abrir(self, incidente: Incidente) -> Incidente:
        """Grava um incidente novo. Se já houver um ativo com a mesma chave, levanta
        `IncidenteAtivoExistente` e a sessão continua utilizável."""
        self._mesmo_tenant(incidente.tenant_id)
        try:
            with self.sessao.begin_nested():
                self.sessao.add(
                    IncidenteModel(
                        tenant_id=incidente.tenant_id,
                        id=incidente.id,
                        origem=incidente.origem,
                        categoria=incidente.categoria.value,
                        ativo=incidente.ativo,
                        chave_correlacao=incidente.chave_correlacao,
                        estado=incidente.estado.value,
                        prioridade=incidente.prioridade.value if incidente.prioridade else None,
                        total_eventos=incidente.total_eventos,
                        contexto=incidente.contexto.model_dump(mode="json"),
                        aberto_em=incidente.aberto_em,
                        atualizado_em=incidente.atualizado_em,
                        reconhecido_em=incidente.reconhecido_em,
                        resolvido_em=incidente.resolvido_em,
                    )
                )
        except IntegrityError as erro:
            if "uq_incidentes_ativo_por_chave" in str(erro.orig):
                raise IncidenteAtivoExistente(incidente.chave_correlacao) from None
            raise
        return incidente

    def obter(self, incidente_id: UUID, bloquear: bool = False) -> Incidente | None:
        linha = self.sessao.get(
            IncidenteModel, (self.tenant, incidente_id), with_for_update=bloquear or None
        )
        return None if linha is None else self._para_dominio(linha)

    def ativo_por_chave(
        self, origem: str, categoria: str, ativo: str | None, bloquear: bool = False
    ) -> Incidente | None:
        """Incidente aberto ou reconhecido com esta chave. Com `bloquear`, trava a linha até o
        fim da transação, para duas correlações concorrentes não disputarem o mesmo incidente."""
        consulta = select(IncidenteModel).where(
            IncidenteModel.tenant_id == self.tenant,
            IncidenteModel.chave_correlacao == chave_correlacao(origem, categoria, ativo),
            IncidenteModel.estado != EstadoIncidente.resolvido.value,
        )
        if bloquear:
            consulta = consulta.with_for_update()
        linha = self.sessao.scalars(consulta).one_or_none()
        return None if linha is None else self._para_dominio(linha)

    def vincular_evento(self, incidente_id: UUID, evento_id: UUID) -> bool:
        """Liga o evento ao incidente e atualiza contagem e horário. Idempotente: devolve False
        se o evento já estava neste incidente; levanta ValueError se estava em outro."""
        ligado = self.sessao.execute(
            update(EventoModel)
            .where(
                EventoModel.tenant_id == self.tenant,
                EventoModel.id == evento_id,
                EventoModel.incidente_id.is_(None),
            )
            .values(incidente_id=incidente_id)
            .returning(EventoModel.ocorrido_em)
        ).scalar_one_or_none()
        if ligado is None:
            atual = self.sessao.scalar(
                select(EventoModel.incidente_id).where(
                    EventoModel.tenant_id == self.tenant, EventoModel.id == evento_id
                )
            )
            if atual == incidente_id:
                return False
            if atual is None:
                raise LookupError(f"evento {evento_id} não existe neste tenant")
            raise ValueError(f"evento {evento_id} já pertence ao incidente {atual}")
        self.sessao.execute(
            update(IncidenteModel)
            .where(IncidenteModel.tenant_id == self.tenant, IncidenteModel.id == incidente_id)
            .values(
                total_eventos=IncidenteModel.total_eventos + 1,
                atualizado_em=func.greatest(IncidenteModel.atualizado_em, ligado),
            )
        )
        return True

    def atualizar_prioridade(
        self, incidente_id: UUID, prioridade: Prioridade, contexto: Contexto | None = None
    ) -> None:
        valores: dict[str, Any] = {"prioridade": prioridade.value}
        if contexto is not None:
            valores["contexto"] = contexto.model_dump(mode="json")
        self._atualizar(incidente_id, valores)

    def reconhecer(self, incidente_id: UUID, quando: datetime) -> bool:
        """Só um incidente aberto pode ser reconhecido; devolve se mudou."""
        return self._transicao(
            incidente_id,
            de=[EstadoIncidente.aberto],
            valores={"estado": EstadoIncidente.reconhecido.value, "reconhecido_em": quando},
        )

    def resolver(self, incidente_id: UUID, quando: datetime) -> bool:
        return self._transicao(
            incidente_id,
            de=[EstadoIncidente.aberto, EstadoIncidente.reconhecido],
            valores={"estado": EstadoIncidente.resolvido.value, "resolvido_em": quando},
        )

    def listar(
        self,
        estado: EstadoIncidente | None = None,
        prioridade: Prioridade | None = None,
        limite: int = 100,
    ) -> list[Incidente]:
        """Mais graves primeiro; entre iguais, os atualizados mais recentemente."""
        consulta = select(IncidenteModel).where(IncidenteModel.tenant_id == self.tenant)
        if estado is not None:
            consulta = consulta.where(IncidenteModel.estado == estado.value)
        if prioridade is not None:
            consulta = consulta.where(IncidenteModel.prioridade == prioridade.value)
        consulta = consulta.order_by(
            IncidenteModel.prioridade.asc().nulls_last(), IncidenteModel.atualizado_em.desc()
        ).limit(limite)
        return [self._para_dominio(linha) for linha in self.sessao.scalars(consulta)]

    def _atualizar(self, incidente_id: UUID, valores: dict[str, Any]) -> None:
        resultado = self.sessao.execute(
            update(IncidenteModel)
            .where(IncidenteModel.tenant_id == self.tenant, IncidenteModel.id == incidente_id)
            .values(**valores)
        )
        if resultado.rowcount == 0:
            raise LookupError(f"incidente {incidente_id} não existe neste tenant")

    def _transicao(
        self, incidente_id: UUID, de: list[EstadoIncidente], valores: dict[str, Any]
    ) -> bool:
        resultado = self.sessao.execute(
            update(IncidenteModel)
            .where(
                IncidenteModel.tenant_id == self.tenant,
                IncidenteModel.id == incidente_id,
                IncidenteModel.estado.in_([e.value for e in de]),
            )
            .values(**valores)
        )
        return resultado.rowcount == 1

    @staticmethod
    def _para_dominio(linha: IncidenteModel) -> Incidente:
        return Incidente(
            id=linha.id,
            tenant_id=linha.tenant_id,
            origem=linha.origem,
            categoria=linha.categoria,
            ativo=linha.ativo,
            estado=linha.estado,
            prioridade=linha.prioridade,
            total_eventos=linha.total_eventos,
            contexto=Contexto.model_validate(linha.contexto),
            aberto_em=linha.aberto_em,
            atualizado_em=linha.atualizado_em,
            reconhecido_em=linha.reconhecido_em,
            resolvido_em=linha.resolvido_em,
        )


# --- decisões ----------------------------------------------------------------------------


class DecisaoRegistrada(BaseModel):
    id: UUID
    tenant_id: str
    evento_id: UUID | None
    incidente_id: UUID | None
    decidido_em: AwareDatetime
    decisao: Decisao


class RepositorioDecisoes(_Repositorio):
    """Decisões são somente inserção: uma reavaliação grava uma decisão nova."""

    def registrar(
        self,
        decisao: Decisao,
        *,
        evento_id: UUID | None = None,
        incidente_id: UUID | None = None,
        decisao_id: UUID | None = None,
    ) -> DecisaoRegistrada:
        if evento_id is None and incidente_id is None:
            raise ValueError("a decisão precisa de um evento ou de um incidente")
        linha = DecisaoModel(
            tenant_id=self.tenant,
            id=decisao_id or uuid4(),
            evento_id=evento_id,
            incidente_id=incidente_id,
            prioridade=decisao.prioridade.value,
            impacto=decisao.impacto.value if decisao.impacto else None,
            urgencia=decisao.urgencia.value if decisao.urgencia else None,
            criticidade=decisao.criticidade.value,
            ativo=decisao.ativo,
            resposta=decisao.resposta,
            politica_versao=decisao.politica_versao,
            prioridade_base=decisao.prioridade_base,
            rastro=decisao.rastro.model_dump(mode="json")["passos"],
            resumo=decisao.rastro.resumo,
        )
        self.sessao.add(linha)
        self.sessao.flush()
        self.sessao.refresh(linha, ["decidido_em"])
        return self._para_registro(linha)

    def obter(self, decisao_id: UUID) -> DecisaoRegistrada | None:
        linha = self.sessao.get(DecisaoModel, (self.tenant, decisao_id))
        return None if linha is None else self._para_registro(linha)

    def do_incidente(self, incidente_id: UUID) -> list[DecisaoRegistrada]:
        """Histórico de decisões do incidente, da mais antiga para a mais recente."""
        consulta = (
            select(DecisaoModel)
            .where(DecisaoModel.tenant_id == self.tenant, DecisaoModel.incidente_id == incidente_id)
            .order_by(DecisaoModel.decidido_em, DecisaoModel.id)
        )
        return [self._para_registro(linha) for linha in self.sessao.scalars(consulta)]

    def ultima_do_incidente(self, incidente_id: UUID) -> DecisaoRegistrada | None:
        historico = self.do_incidente(incidente_id)
        return historico[-1] if historico else None

    @staticmethod
    def _para_registro(linha: DecisaoModel) -> DecisaoRegistrada:
        decisao = Decisao(
            prioridade=linha.prioridade,
            impacto=linha.impacto,
            urgencia=linha.urgencia,
            ativo=linha.ativo,
            criticidade=linha.criticidade,
            resposta=linha.resposta,
            politica_versao=linha.politica_versao,
            prioridade_base=linha.prioridade_base,
            rastro=Rastro(passos=linha.rastro),
        )
        return DecisaoRegistrada(
            id=linha.id,
            tenant_id=linha.tenant_id,
            evento_id=linha.evento_id,
            incidente_id=linha.incidente_id,
            decidido_em=linha.decidido_em,
            decisao=decisao,
        )


# --- notificações ------------------------------------------------------------------------


class RepositorioNotificacoes(_Repositorio):
    def registrar(self, notificacao: Notificacao) -> Notificacao:
        self._mesmo_tenant(notificacao.tenant_id)
        self.sessao.add(
            NotificacaoModel(
                **notificacao.model_dump(exclude={"prioridade", "modo", "estado"}),
                prioridade=notificacao.prioridade.value,
                modo=notificacao.modo.value,
                estado=notificacao.estado.value,
            )
        )
        self.sessao.flush()
        return notificacao

    def obter(self, notificacao_id: UUID) -> Notificacao | None:
        linha = self.sessao.get(NotificacaoModel, (self.tenant, notificacao_id))
        return None if linha is None else self._para_dominio(linha)

    def reservar_pendentes(self, limite: int = 10) -> list[Notificacao]:
        """Pendentes mais antigas, travadas até o fim da transação. Com SKIP LOCKED, dois
        workers nunca pegam a mesma notificação."""
        consulta = (
            select(NotificacaoModel)
            .where(
                NotificacaoModel.tenant_id == self.tenant,
                NotificacaoModel.estado == EstadoNotificacao.pendente.value,
            )
            .order_by(NotificacaoModel.criada_em, NotificacaoModel.id)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        return [self._para_dominio(linha) for linha in self.sessao.scalars(consulta)]

    def marcar_enviada(
        self, notificacao_id: UUID, id_externo: str | None, quando: datetime
    ) -> None:
        self._atualizar(
            notificacao_id,
            estado=EstadoNotificacao.enviada.value,
            id_externo=id_externo,
            enviada_em=quando,
            motivo=None,
        )

    def marcar_falha(self, notificacao_id: UUID, erro: str, max_tentativas: int = 3) -> Notificacao:
        """Conta a tentativa. Volta para pendente até esgotar as tentativas; depois, falhou."""
        tentativas = NotificacaoModel.tentativas + 1
        linha = self.sessao.execute(
            update(NotificacaoModel)
            .where(NotificacaoModel.tenant_id == self.tenant, NotificacaoModel.id == notificacao_id)
            .values(
                tentativas=tentativas,
                motivo=erro,
                estado=case(
                    (tentativas >= max_tentativas, EstadoNotificacao.falhou.value),
                    else_=EstadoNotificacao.pendente.value,
                ),
            )
            .returning(NotificacaoModel)
        ).scalar_one_or_none()
        if linha is None:
            raise LookupError(f"notificação {notificacao_id} não existe neste tenant")
        return self._para_dominio(linha)

    def reconhecer(self, notificacao_id: UUID, por: str, quando: datetime) -> bool:
        """Registra o reconhecimento (botão no Telegram). Só o primeiro vale."""
        resultado = self.sessao.execute(
            update(NotificacaoModel)
            .where(
                NotificacaoModel.tenant_id == self.tenant,
                NotificacaoModel.id == notificacao_id,
                NotificacaoModel.reconhecida_em.is_(None),
            )
            .values(reconhecida_em=quando, reconhecida_por=por)
        )
        return resultado.rowcount == 1

    def do_incidente(self, incidente_id: UUID) -> list[Notificacao]:
        consulta = (
            select(NotificacaoModel)
            .where(
                NotificacaoModel.tenant_id == self.tenant,
                NotificacaoModel.incidente_id == incidente_id,
            )
            .order_by(NotificacaoModel.criada_em, NotificacaoModel.id)
        )
        return [self._para_dominio(linha) for linha in self.sessao.scalars(consulta)]

    def _atualizar(self, notificacao_id: UUID, **valores: Any) -> None:
        resultado = self.sessao.execute(
            update(NotificacaoModel)
            .where(NotificacaoModel.tenant_id == self.tenant, NotificacaoModel.id == notificacao_id)
            .values(**valores)
        )
        if resultado.rowcount == 0:
            raise LookupError(f"notificação {notificacao_id} não existe neste tenant")

    @staticmethod
    def _para_dominio(linha: NotificacaoModel) -> Notificacao:
        campos = Notificacao.model_fields
        return Notificacao.model_validate({nome: getattr(linha, nome) for nome in campos})


# --- auditoria ---------------------------------------------------------------------------


class EntradaAuditoria(BaseModel):
    id: int
    tenant_id: str
    ocorrido_em: AwareDatetime
    ator: str
    acao: str
    entidade: str
    entidade_id: str | None
    dados: dict[str, Any] = Field(default_factory=dict)


class RepositorioAuditoria(_Repositorio):
    """Trilha somente inserção de quem fez o quê: mudanças de política, reconhecimentos etc."""

    def registrar(
        self,
        ator: str,
        acao: str,
        entidade: str,
        entidade_id: str | UUID | None = None,
        dados: dict[str, Any] | None = None,
    ) -> EntradaAuditoria:
        linha = self.sessao.execute(
            insert(AuditoriaModel)
            .values(
                tenant_id=self.tenant,
                ator=ator,
                acao=acao,
                entidade=entidade,
                entidade_id=None if entidade_id is None else str(entidade_id),
                dados=dados or {},
            )
            .returning(AuditoriaModel)
        ).scalar_one()
        return EntradaAuditoria.model_validate(linha, from_attributes=True)

    def listar(
        self, entidade: str | None = None, entidade_id: str | UUID | None = None, limite: int = 100
    ) -> list[EntradaAuditoria]:
        """Mais recentes primeiro."""
        consulta = select(AuditoriaModel).where(AuditoriaModel.tenant_id == self.tenant)
        if entidade is not None:
            consulta = consulta.where(AuditoriaModel.entidade == entidade)
        if entidade_id is not None:
            consulta = consulta.where(AuditoriaModel.entidade_id == str(entidade_id))
        consulta = consulta.order_by(AuditoriaModel.id.desc()).limit(limite)
        return [
            EntradaAuditoria.model_validate(linha, from_attributes=True)
            for linha in self.sessao.scalars(consulta)
        ]


# --- tokens de ingestão --------------------------------------------------------------------

PREFIXO_TOKEN = "rnd_"


def gerar_token() -> str:
    """Token novo, com prefixo reconhecível (ajuda a achar vazamento em log e em repositório)."""
    return PREFIXO_TOKEN + secrets.token_urlsafe(32)


def hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenIngestao(BaseModel):
    id: UUID
    tenant_id: str
    nome: str
    criado_em: AwareDatetime
    revogado_em: AwareDatetime | None


class RepositorioTokens(_Repositorio):
    """Tokens de ingestão do tenant. O token em claro só existe na resposta de `criar`."""

    def criar(self, nome: str) -> tuple[str, TokenIngestao]:
        token = gerar_token()
        linha = TokenIngestaoModel(
            tenant_id=self.tenant, id=uuid4(), nome=nome, hash=hash_do_token(token)
        )
        self.sessao.add(linha)
        self.sessao.flush()
        self.sessao.refresh(linha, ["criado_em"])
        return token, TokenIngestao.model_validate(linha, from_attributes=True)

    def listar(self) -> list[TokenIngestao]:
        consulta = (
            select(TokenIngestaoModel)
            .where(TokenIngestaoModel.tenant_id == self.tenant)
            .order_by(TokenIngestaoModel.criado_em)
        )
        return [
            TokenIngestao.model_validate(linha, from_attributes=True)
            for linha in self.sessao.scalars(consulta)
        ]

    def revogar(self, token_id: UUID, quando: datetime) -> bool:
        resultado = self.sessao.execute(
            update(TokenIngestaoModel)
            .where(
                TokenIngestaoModel.tenant_id == self.tenant,
                TokenIngestaoModel.id == token_id,
                TokenIngestaoModel.revogado_em.is_(None),
            )
            .values(revogado_em=quando)
        )
        return resultado.rowcount == 1
