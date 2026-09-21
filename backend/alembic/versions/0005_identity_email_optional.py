"""make identity email / email_provider nullable

Identities can now exist before their mailbox does - the email pipeline
attaches email / email_provider / email_password once it finishes creating
the account, instead of a fake placeholder being generated up front.

Revision ID: 0005_identity_email_optional
Revises: 0004_remove_platform_table
Create Date: 2026-09-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_identity_email_optional"
down_revision: Union[str, None] = "0004_remove_platform_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "identities" not in inspector.get_table_names():
        return

    with op.batch_alter_table("identities") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=256), nullable=True)
        batch_op.alter_column("email_provider", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "identities" not in inspector.get_table_names():
        return

    with op.batch_alter_table("identities") as batch_op:
        batch_op.alter_column("email_provider", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("email", existing_type=sa.String(length=256), nullable=False)
