"""ai research studies

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-06 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "studies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("objective", sa.JSON(), nullable=False),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_studies_project_id"), "studies", ["project_id"], unique=False)
    op.create_index(op.f("ix_studies_status"), "studies", ["status"], unique=False)

    op.add_column("experiments", sa.Column("study_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_experiments_study_id"), "experiments", ["study_id"], unique=False)
    op.create_foreign_key(
        "fk_experiments_study_id", "experiments", "studies", ["study_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("fk_experiments_study_id", "experiments", type_="foreignkey")
    op.drop_index(op.f("ix_experiments_study_id"), table_name="experiments")
    op.drop_column("experiments", "study_id")
    op.drop_index(op.f("ix_studies_status"), table_name="studies")
    op.drop_index(op.f("ix_studies_project_id"), table_name="studies")
    op.drop_table("studies")
