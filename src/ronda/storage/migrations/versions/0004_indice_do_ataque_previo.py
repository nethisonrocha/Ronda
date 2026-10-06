"""Índice do ataque prévio no ativo.

`incidentes (tenant_id, ativo, atualizado_em)`: o pipeline pergunta, a cada evento, se o mesmo
ativo teve outro incidente P1/P2 nas últimas 24 h (o contexto `ataque_previo_no_ativo`, decisão
A5 do dono em 06/10/2026).

Revisão: 0004
Anterior: 0003
Criada em: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_incidentes_tenant_id_ativo_atualizado_em",
        "incidentes",
        ["tenant_id", "ativo", "atualizado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_incidentes_tenant_id_ativo_atualizado_em", table_name="incidentes")
