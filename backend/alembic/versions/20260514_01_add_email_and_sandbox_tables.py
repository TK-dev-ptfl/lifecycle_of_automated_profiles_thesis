"""initial schema

Revision ID: 0001_init
Revises:
Create Date: 2026-05-14 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platforms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("api_key", sa.String(length=512), nullable=True),
        sa.Column("api_secret", sa.String(length=512), nullable=True),
        sa.Column("rate_limits", sa.JSON(), nullable=False),
        sa.Column("adapter_config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("email_provider", sa.String(length=64), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("phone_provider", sa.String(length=64), nullable=True),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("profile_photo_url", sa.String(length=512), nullable=True),
        sa.Column("bio", sa.String(length=1024), nullable=True),
        sa.Column("location", sa.String(length=128), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("interests", sa.JSON(), nullable=False),
        sa.Column("browser_profile_id", sa.String(length=256), nullable=False),
        sa.Column("browser_profile_provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "proxies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("host", sa.String(length=256), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("password", sa.String(length=256), nullable=True),
        sa.Column("protocol", sa.String(length=6), nullable=False),
        sa.Column("type", sa.String(length=11), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("assigned_bot_id", sa.UUID(), nullable=True),
        sa.Column("is_healthy", sa.Boolean(), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["assigned_bot_id"], ["bots.id"]),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("platform_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("sync_mode", sa.String(length=11), nullable=False),
        sa.Column("success_criteria", sa.JSON(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"]),
    )

    op.create_table(
        "bots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("platform_id", sa.UUID(), nullable=False),
        sa.Column("identity_id", sa.UUID(), nullable=True),
        sa.Column("proxy_id", sa.UUID(), nullable=True),
        sa.Column("skeleton", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=11), nullable=False),
        sa.Column("status", sa.String(length=7), nullable=False),
        sa.Column("communication_mode", sa.String(length=15), nullable=False),
        sa.Column("behaviour_pattern", sa.String(length=10), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("algorithm_config", sa.JSON(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("flag_count", sa.Integer(), nullable=False),
        sa.Column("last_active", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("password", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"]),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"]),
        sa.ForeignKeyConstraint(["proxy_id"], ["proxies.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
    )

    op.create_table(
        "logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("bot_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("level", sa.String(length=5), nullable=False),
        sa.Column("category", sa.String(length=9), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
    )

    op.create_table(
        "email_platforms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=14), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("domain", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "emails",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=14), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("address", sa.String(length=256), nullable=False),
        sa.Column("password", sa.String(length=256), nullable=True),
        sa.Column("used_by_bot_id", sa.UUID(), nullable=True),
        sa.Column("ever_blocked", sa.Boolean(), nullable=False),
        sa.Column("blocked_on_platforms", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["email_platforms.id"]),
        sa.ForeignKeyConstraint(["used_by_bot_id"], ["bots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("address"),
    )

    op.create_table(
        "sandboxes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("groupname", sa.String(length=256), nullable=False),
        sa.Column("profile", sa.String(length=256), nullable=False),
        sa.Column("password", sa.String(length=256), nullable=False),
        sa.Column("bot_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("sandboxes")
    op.drop_table("emails")
    op.drop_table("email_platforms")
    op.drop_table("logs")
    op.drop_table("bots")
    op.drop_table("tasks")
    op.drop_table("proxies")
    op.drop_table("identities")
    op.drop_table("platforms")
