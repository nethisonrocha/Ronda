"""Esquema inicial: tenants, eventos, incidentes, decisões, notificações e auditoria.

- Chaves primárias e estrangeiras compostas com tenant_id.
- Row-Level Security com FORCE em todas as tabelas, por `app.tenant_id` (definido por
  transação com `set_config('app.tenant_id', ..., true)`). Sem tenant definido, nada é visível
  e nada pode ser gravado.
- `decisoes` e `auditoria` são somente inserção: UPDATE e DELETE são recusados por trigger.

Os papéis e os GRANTs não são criados aqui, porque dependem do ambiente (veja
deploy/compose/initdb e os testes de integração).

Revisão: 0001
Anterior:
Criada em: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIORIDADES = "'P1', 'P2', 'P3', 'P4'"
TABELAS_DE_TENANT = ("eventos", "incidentes", "decisoes", "notificacoes", "auditoria")
TABELAS_SOMENTE_INSERCAO = ("decisoes", "auditoria")
TENANT_ATUAL = "current_setting('app.tenant_id', true)"


def _tenant_id() -> sa.Column:
    return sa.Column("tenant_id", sa.String(63), nullable=False)


def _fk_tenant(tabela: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name=f"fk_{tabela}_tenant_id_tenants"
    )


def _momento(nome: str, *, nulo: bool = False, agora: bool = False) -> sa.Column:
    return sa.Column(
        nome,
        sa.DateTime(timezone=True),
        nullable=nulo,
        server_default=sa.func.now() if agora else None,
    )


def _jsonb_vazio(nome: str) -> sa.Column:
    return sa.Column(
        nome, postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
    )


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(63), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        _momento("criado_em", agora=True),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.CheckConstraint("id ~ '^[a-z0-9][a-z0-9-]{0,62}$'", name="ck_tenants_id_valido"),
    )

    op.create_table(
        "incidentes",
        _tenant_id(),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Text(), nullable=True),
        sa.Column("chave_correlacao", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False, server_default=sa.text("'aberto'")),
        sa.Column("prioridade", sa.Text(), nullable=True),
        sa.Column("total_eventos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _jsonb_vazio("contexto"),
        _momento("aberto_em"),
        _momento("atualizado_em"),
        _momento("reconhecido_em", nulo=True),
        _momento("resolvido_em", nulo=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_incidentes"),
        _fk_tenant("incidentes"),
        sa.CheckConstraint(
            "estado IN ('aberto', 'reconhecido', 'resolvido')", name="ck_incidentes_estado"
        ),
        sa.CheckConstraint(f"prioridade IN ({PRIORIDADES})", name="ck_incidentes_prioridade"),
        sa.CheckConstraint("total_eventos >= 0", name="ck_incidentes_total_eventos"),
    )
    op.create_index(
        "uq_incidentes_ativo_por_chave",
        "incidentes",
        ["tenant_id", "chave_correlacao"],
        unique=True,
        postgresql_where=sa.text("estado <> 'resolvido'"),
    )
    op.create_index(
        "ix_incidentes_tenant_id_estado_prioridade",
        "incidentes",
        ["tenant_id", "estado", "prioridade"],
    )

    op.create_table(
        "eventos",
        _tenant_id(),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("id_origem", sa.Text(), nullable=True),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("severidade_origem", postgresql.JSONB(), nullable=True),
        sa.Column("ip_origem", postgresql.INET(), nullable=True),
        sa.Column("ip_destino", postgresql.INET(), nullable=True),
        sa.Column("ativo", sa.Text(), nullable=True),
        _momento("ocorrido_em"),
        _momento("recebido_em", agora=True),
        _jsonb_vazio("evidencias"),
        _jsonb_vazio("bruto"),
        sa.Column("incidente_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_eventos"),
        _fk_tenant("eventos"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "incidente_id"],
            ["incidentes.tenant_id", "incidentes.id"],
            name="fk_eventos_tenant_id_incidente_id_incidentes",
        ),
    )
    op.create_index(
        "uq_eventos_origem_id_origem",
        "eventos",
        ["tenant_id", "origem", "id_origem"],
        unique=True,
        postgresql_where=sa.text("id_origem IS NOT NULL"),
    )
    op.create_index("ix_eventos_tenant_id_ocorrido_em", "eventos", ["tenant_id", "ocorrido_em"])
    op.create_index("ix_eventos_tenant_id_incidente_id", "eventos", ["tenant_id", "incidente_id"])

    op.create_table(
        "decisoes",
        _tenant_id(),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evento_id", sa.Uuid(), nullable=True),
        sa.Column("incidente_id", sa.Uuid(), nullable=True),
        sa.Column("prioridade", sa.Text(), nullable=False),
        sa.Column("impacto", sa.Text(), nullable=True),
        sa.Column("urgencia", sa.Text(), nullable=True),
        sa.Column("criticidade", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Text(), nullable=True),
        sa.Column("resposta", sa.Interval(), nullable=True),
        sa.Column("politica_versao", sa.Integer(), nullable=False),
        sa.Column("prioridade_base", sa.Boolean(), nullable=False),
        sa.Column("rastro", postgresql.JSONB(), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=False),
        _momento("decidido_em", agora=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_decisoes"),
        _fk_tenant("decisoes"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evento_id"],
            ["eventos.tenant_id", "eventos.id"],
            name="fk_decisoes_tenant_id_evento_id_eventos",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "incidente_id"],
            ["incidentes.tenant_id", "incidentes.id"],
            name="fk_decisoes_tenant_id_incidente_id_incidentes",
        ),
        sa.CheckConstraint(
            "evento_id IS NOT NULL OR incidente_id IS NOT NULL",
            name="ck_decisoes_evento_ou_incidente",
        ),
        sa.CheckConstraint(f"prioridade IN ({PRIORIDADES})", name="ck_decisoes_prioridade"),
        sa.CheckConstraint(
            "criticidade IN ('baixa', 'media', 'alta')", name="ck_decisoes_criticidade"
        ),
        sa.CheckConstraint("impacto IN ('baixo', 'medio', 'alto')", name="ck_decisoes_impacto"),
        sa.CheckConstraint("urgencia IN ('baixa', 'media', 'alta')", name="ck_decisoes_urgencia"),
        sa.CheckConstraint("jsonb_typeof(rastro) = 'array'", name="ck_decisoes_rastro_lista"),
    )
    op.create_index(
        "ix_decisoes_tenant_id_incidente_id_decidido_em",
        "decisoes",
        ["tenant_id", "incidente_id", "decidido_em"],
    )
    op.create_index("ix_decisoes_tenant_id_evento_id", "decisoes", ["tenant_id", "evento_id"])

    op.create_table(
        "notificacoes",
        _tenant_id(),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incidente_id", sa.Uuid(), nullable=False),
        sa.Column("decisao_id", sa.Uuid(), nullable=True),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("destino", sa.Text(), nullable=False),
        sa.Column("prioridade", sa.Text(), nullable=False),
        sa.Column("modo", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False, server_default=sa.text("'pendente'")),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("id_externo", sa.Text(), nullable=True),
        _momento("criada_em", agora=True),
        _momento("enviada_em", nulo=True),
        _momento("reconhecida_em", nulo=True),
        sa.Column("reconhecida_por", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_notificacoes"),
        _fk_tenant("notificacoes"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "incidente_id"],
            ["incidentes.tenant_id", "incidentes.id"],
            name="fk_notificacoes_tenant_id_incidente_id_incidentes",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "decisao_id"],
            ["decisoes.tenant_id", "decisoes.id"],
            name="fk_notificacoes_tenant_id_decisao_id_decisoes",
        ),
        sa.CheckConstraint(f"prioridade IN ({PRIORIDADES})", name="ck_notificacoes_prioridade"),
        sa.CheckConstraint(
            "modo IN ('imediata', 'agrupada', 'resumo_diario')", name="ck_notificacoes_modo"
        ),
        sa.CheckConstraint(
            "estado IN ('pendente', 'enviada', 'falhou', 'suprimida')",
            name="ck_notificacoes_estado",
        ),
        sa.CheckConstraint("tentativas >= 0", name="ck_notificacoes_tentativas"),
    )
    op.create_index(
        "ix_notificacoes_tenant_id_estado_criada_em",
        "notificacoes",
        ["tenant_id", "estado", "criada_em"],
    )
    op.create_index(
        "ix_notificacoes_tenant_id_incidente_id", "notificacoes", ["tenant_id", "incidente_id"]
    )

    op.create_table(
        "auditoria",
        _tenant_id(),
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        _momento("ocorrido_em", agora=True),
        sa.Column("ator", sa.Text(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("entidade", sa.Text(), nullable=False),
        sa.Column("entidade_id", sa.Text(), nullable=True),
        _jsonb_vazio("dados"),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_auditoria"),
        _fk_tenant("auditoria"),
    )
    op.create_index("ix_auditoria_tenant_id_ocorrido_em", "auditoria", ["tenant_id", "ocorrido_em"])
    op.create_index(
        "ix_auditoria_tenant_id_entidade_entidade_id",
        "auditoria",
        ["tenant_id", "entidade", "entidade_id"],
    )

    # --- Row-Level Security ----------------------------------------------------------------
    for tabela in ("tenants", *TABELAS_DE_TENANT):
        coluna = "id" if tabela == "tenants" else "tenant_id"
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        # FORCE: vale também para o dono da tabela (superusuários continuam isentos).
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY isolamento_tenant ON {tabela} "
            f"USING ({coluna} = {TENANT_ATUAL}) WITH CHECK ({coluna} = {TENANT_ATUAL})"
        )

    # --- Somente inserção --------------------------------------------------------------------
    op.execute(
        """
        CREATE FUNCTION ronda_somente_insercao() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'a tabela % é somente inserção: % recusado', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    for tabela in TABELAS_SOMENTE_INSERCAO:
        op.execute(
            f"CREATE TRIGGER {tabela}_somente_insercao BEFORE UPDATE OR DELETE ON {tabela} "
            "FOR EACH ROW EXECUTE FUNCTION ronda_somente_insercao()"
        )


def downgrade() -> None:
    for tabela in TABELAS_SOMENTE_INSERCAO:
        op.execute(f"DROP TRIGGER IF EXISTS {tabela}_somente_insercao ON {tabela}")
    op.execute("DROP FUNCTION IF EXISTS ronda_somente_insercao()")
    for tabela in ("auditoria", "notificacoes", "decisoes", "eventos", "incidentes", "tenants"):
        op.drop_table(tabela)
