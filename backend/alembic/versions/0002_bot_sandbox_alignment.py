"""align sandbox and bot tracking fields

Revision ID: 0002_bot_sandbox_alignment
Revises: 0001_init
Create Date: 2026-05-14 13:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_bot_sandbox_alignment"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "sandboxes" in inspector.get_table_names():
        sandbox_cols = {col["name"] for col in inspector.get_columns("sandboxes")}
        with op.batch_alter_table("sandboxes") as batch_op:
            if "profile" in sandbox_cols and "name" not in sandbox_cols:
                batch_op.alter_column("profile", new_column_name="name")
            if "bot_ids" in sandbox_cols:
                batch_op.drop_column("bot_ids")

    if "bots" in inspector.get_table_names():
        bot_cols = {col["name"] for col in inspector.get_columns("bots")}
        with op.batch_alter_table("bots") as batch_op:
            if "identity" not in bot_cols:
                batch_op.add_column(sa.Column("identity", sa.String(length=256), nullable=True))
            if "profile_name" not in bot_cols:
                batch_op.add_column(sa.Column("profile_name", sa.String(length=256), nullable=True))
            if "profile_password" not in bot_cols:
                batch_op.add_column(sa.Column("profile_password", sa.String(length=256), nullable=True))
            if "platform_name" not in bot_cols:
                batch_op.add_column(sa.Column("platform_name", sa.String(length=128), nullable=True))
            if "is_healthy" not in bot_cols:
                batch_op.add_column(sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.true()))
            if "sandbox_ids" not in bot_cols:
                batch_op.add_column(sa.Column("sandbox_ids", sa.JSON(), nullable=False, server_default="[]"))
            if "state" not in bot_cols:
                batch_op.add_column(sa.Column("state", sa.String(length=32), nullable=False, server_default="not_active"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "bots" in inspector.get_table_names():
        bot_cols = {col["name"] for col in inspector.get_columns("bots")}
        with op.batch_alter_table("bots") as batch_op:
            if "state" in bot_cols:
                batch_op.drop_column("state")
            if "sandbox_ids" in bot_cols:
                batch_op.drop_column("sandbox_ids")
            if "is_healthy" in bot_cols:
                batch_op.drop_column("is_healthy")
            if "platform_name" in bot_cols:
                batch_op.drop_column("platform_name")
            if "profile_password" in bot_cols:
                batch_op.drop_column("profile_password")
            if "profile_name" in bot_cols:
                batch_op.drop_column("profile_name")
            if "identity" in bot_cols:
                batch_op.drop_column("identity")

    if "sandboxes" in inspector.get_table_names():
        sandbox_cols = {col["name"] for col in inspector.get_columns("sandboxes")}
        with op.batch_alter_table("sandboxes") as batch_op:
            if "bot_ids" not in sandbox_cols:
                batch_op.add_column(sa.Column("bot_ids", sa.JSON(), nullable=False, server_default="[]"))
            if "name" in sandbox_cols and "profile" not in sandbox_cols:
                batch_op.alter_column("name", new_column_name="profile")

