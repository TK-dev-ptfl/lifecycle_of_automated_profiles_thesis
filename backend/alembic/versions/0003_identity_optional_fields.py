"""add missing optional identity fields

Revision ID: 0003_identity_optional_fields
Revises: 0002_bot_sandbox_alignment
Create Date: 2026-05-14 18:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_identity_optional_fields"
down_revision: Union[str, None] = "0002_bot_sandbox_alignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "identities" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("identities")}
    with op.batch_alter_table("identities") as batch_op:
        if "email_password" not in cols:
            batch_op.add_column(sa.Column("email_password", sa.String(length=256), nullable=True))
        if "phone_number" not in cols:
            batch_op.add_column(sa.Column("phone_number", sa.String(length=32), nullable=True))
        if "phone_provider" not in cols:
            batch_op.add_column(sa.Column("phone_provider", sa.String(length=64), nullable=True))
        if "profile_photo_url" not in cols:
            batch_op.add_column(sa.Column("profile_photo_url", sa.String(length=512), nullable=True))
        if "bio" not in cols:
            batch_op.add_column(sa.Column("bio", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "identities" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("identities")}
    with op.batch_alter_table("identities") as batch_op:
        if "bio" in cols:
            batch_op.drop_column("bio")
        if "profile_photo_url" in cols:
            batch_op.drop_column("profile_photo_url")
        if "phone_provider" in cols:
            batch_op.drop_column("phone_provider")
        if "phone_number" in cols:
            batch_op.drop_column("phone_number")
        if "email_password" in cols:
            batch_op.drop_column("email_password")
