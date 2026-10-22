"""Sin narración: las páginas ya no guardan audio

Revisión: 0002
Anterior: 0001
Fecha: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("paginas") as tabla:
        tabla.drop_column("audio_clave")


def downgrade() -> None:
    with op.batch_alter_table("paginas") as tabla:
        tabla.add_column(sa.Column("audio_clave", sa.String(255)))
