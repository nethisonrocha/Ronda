"""Índices da correlação.

- `incidentes (tenant_id, chave_correlacao)`, em qualquer estado: a recorrência conta os eventos
  da chave nas últimas 24 h, inclusive de incidentes já encerrados.
- `eventos (tenant_id, incidente_id, ocorrido_em)` no lugar de `(tenant_id, incidente_id)`: a
  mesma busca por incidente, agora já ordenada pelo horário da janela de 24 h.

Revisão: 0003
Anterior: 0002
Criada em: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_incidentes_tenant_id_chave_correlacao",
        "incidentes",
        ["tenant_id", "chave_correlacao"],
    )
    op.create_index(
        "ix_eventos_tenant_id_incidente_id_ocorrido_em",
        "eventos",
        ["tenant_id", "incidente_id", "ocorrido_em"],
    )
    op.drop_index("ix_eventos_tenant_id_incidente_id", table_name="eventos")


def downgrade() -> None:
    op.create_index("ix_eventos_tenant_id_incidente_id", "eventos", ["tenant_id", "incidente_id"])
    op.drop_index("ix_eventos_tenant_id_incidente_id_ocorrido_em", table_name="eventos")
    op.drop_index("ix_incidentes_tenant_id_chave_correlacao", table_name="incidentes")
