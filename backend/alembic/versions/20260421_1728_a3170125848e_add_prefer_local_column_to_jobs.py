"""add prefer_local column to jobs

Revision ID: a3170125848e
Revises: f74975c08dfb
Create Date: 2026-04-21 17:28:33.102021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identifiants de révision utilisés par Alembic.
revision: str = 'a3170125848e'
down_revision: Union[str, None] = 'f74975c08dfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Applique la migration."""
    op.add_column("jobs", sa.Column("prefer_local", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Annule la migration."""
    op.drop_column("jobs", "prefer_local")
