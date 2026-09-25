"""Tokens de ingestão por tenant.

- Tabela `tokens_ingestao` guarda só o sha256 do token, com o nome e a revogação.
- RLS ligada **sem FORCE**: a função `ronda_tenant_do_token`, SECURITY DEFINER e do dono,
  precisa achar o tenant pelo hash antes de existir um tenant na sessão. O papel da aplicação
  continua sujeito à política `isolamento_tenant`.

Revisão: 0002
Anterior: 0001
Criada em: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_ATUAL = "current_setting('app.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "tokens_ingestao",
        sa.Column("tenant_id", sa.String(63), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_tokens_ingestao"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_tokens_ingestao_tenant_id_tenants"
        ),
    )
    op.create_index("uq_tokens_ingestao_hash", "tokens_ingestao", ["hash"], unique=True)

    op.execute("ALTER TABLE tokens_ingestao ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY isolamento_tenant ON tokens_ingestao "
        f"USING (tenant_id = {TENANT_ATUAL}) WITH CHECK (tenant_id = {TENANT_ATUAL})"
    )
    op.execute(
        """
        CREATE FUNCTION ronda_tenant_do_token(hash_token text) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT tenant_id FROM tokens_ingestao
            WHERE hash = hash_token AND revogado_em IS NULL
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ronda_tenant_do_token(text)")
    op.drop_table("tokens_ingestao")
