"""realtime drug injection

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-08 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drug Interaction Studio — real-time injection.
    op.add_column("simulations", sa.Column("drug_regimen", sa.JSON(), nullable=True))
    op.add_column("simulations", sa.Column("drug_commands", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("simulations", "drug_commands")
    op.drop_column("simulations", "drug_regimen")
