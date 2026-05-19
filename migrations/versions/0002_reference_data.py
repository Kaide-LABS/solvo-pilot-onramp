"""reference_data — UN/LOCODE + WCO HS6 reference tables.

Implements PHASE_3_SPEC.md §5.

Revision ID: 0002_reference_data
Revises: 0001_initial
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_reference_data"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create un_locode_reference, wco_hs6_reference, carrier_port_aliases."""
    op.create_table(
        "un_locode_reference",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("country_code", sa.Text, nullable=False),
        sa.Column("place_name", sa.Text, nullable=False),
        sa.Column("subdivision", sa.Text, nullable=True),
        sa.Column("function", sa.Text, nullable=False),
        sa.Column("latitude", sa.Numeric(6, 4), nullable=True),
        sa.Column("longitude", sa.Numeric(7, 4), nullable=True),
    )
    op.create_index("ix_un_locode_country", "un_locode_reference", ["country_code"])
    op.create_index(
        "ix_un_locode_place_lower",
        "un_locode_reference",
        [sa.text("LOWER(place_name)")],
    )

    op.create_table(
        "wco_hs6_reference",
        sa.Column("hs6", sa.Text, primary_key=True),
        sa.Column("chapter", sa.Text, nullable=False),
        sa.Column("heading", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
    )

    op.create_table(
        "carrier_port_aliases",
        sa.Column("alias", sa.Text, primary_key=True),
        sa.Column(
            "canonical",
            sa.Text,
            sa.ForeignKey("un_locode_reference.code"),
            nullable=False,
        ),
        sa.Column("source", sa.Text, nullable=False),
    )


def downgrade() -> None:
    """Drop reference-data tables in dependency order."""
    op.drop_table("carrier_port_aliases")
    op.drop_table("wco_hs6_reference")
    op.drop_index("ix_un_locode_place_lower", table_name="un_locode_reference")
    op.drop_index("ix_un_locode_country", table_name="un_locode_reference")
    op.drop_table("un_locode_reference")
