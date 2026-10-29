"""Narración por voz: las páginas guardan la clave de su audio (opcional)

Revisión: 0003
Anterior: 0002
Fecha: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("paginas") as tabla:
        tabla.add_column(sa.Column("audio_clave", sa.String(255)))


def downgrade() -> None:
    with op.batch_alter_table("paginas") as tabla:
        tabla.drop_column("audio_clave")
