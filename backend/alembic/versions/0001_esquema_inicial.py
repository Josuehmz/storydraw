"""Esquema inicial: tutores, consentimientos, perfiles, cuentos, páginas y moderación

Revisión: 0001
Anterior: ninguna
Fecha: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tutores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hash_contrasena", sa.String(255), nullable=False),
        sa.Column("verificado", sa.Boolean(), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tutores_email", "tutores", ["email"], unique=True)

    op.create_table(
        "consentimientos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tutor_id", sa.Uuid(), sa.ForeignKey("tutores.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("aceptado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_consentimientos_tutor_id", "consentimientos", ["tutor_id"])

    op.create_table(
        "perfiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tutor_id", sa.Uuid(), sa.ForeignKey("tutores.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("apodo", sa.String(40), nullable=False),
        sa.Column("edad", sa.SmallInteger(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("edad BETWEEN 6 AND 12", name="ck_perfiles_edad"),
    )
    op.create_index("ix_perfiles_tutor_id", "perfiles", ["tutor_id"])

    op.create_table(
        "cuentos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "perfil_id", sa.Uuid(), sa.ForeignKey("perfiles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "tutor_id", sa.Uuid(), sa.ForeignKey("tutores.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(200)),
        sa.Column("personaje", sa.String(120)),
        sa.Column("avisos", sa.JSON(), nullable=False),
        sa.Column("pasos", sa.JSON(), nullable=False),
        sa.Column("latencia_ms", sa.Integer()),
        sa.Column("costo_usd", sa.Float()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminado_en", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_cuentos_perfil_id", "cuentos", ["perfil_id"])
    op.create_index("ix_cuentos_tutor_id", "cuentos", ["tutor_id"])
    op.create_index("ix_cuentos_estado", "cuentos", ["estado"])

    op.create_table(
        "paginas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cuento_id", sa.Uuid(), sa.ForeignKey("cuentos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("numero", sa.SmallInteger(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("imagen_clave", sa.String(255), nullable=False),
        sa.Column("audio_clave", sa.String(255)),
        sa.UniqueConstraint("cuento_id", "numero", name="uq_pagina_numero"),
    )
    op.create_index("ix_paginas_cuento_id", "paginas", ["cuento_id"])

    op.create_table(
        "registros_moderacion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cuento_id", sa.Uuid(), sa.ForeignKey("cuentos.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("origen", sa.String(20), nullable=False),
        sa.Column("texto", sa.Text()),
        sa.Column("categorias", sa.JSON(), nullable=False),
        sa.Column("revisado", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_registros_moderacion_cuento_id", "registros_moderacion", ["cuento_id"])
    op.create_index("ix_registros_moderacion_revisado", "registros_moderacion", ["revisado"])


def downgrade() -> None:
    op.drop_table("registros_moderacion")
    op.drop_table("paginas")
    op.drop_table("cuentos")
    op.drop_table("perfiles")
    op.drop_table("consentimientos")
    op.drop_table("tutores")
