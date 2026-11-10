"""Tope diario de cuentos con voz: una fila por día UTC con los cuentos narrados

Revisión: 0004
Anterior: 0003
Fecha: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cupos_voz",
        sa.Column("dia", sa.Date(), primary_key=True),
        sa.Column("usados", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("cupos_voz")
