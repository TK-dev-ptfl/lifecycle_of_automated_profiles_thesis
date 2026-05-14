"""remove platforms table and platform foreign keys

Revision ID: 0004_remove_platform_table
Revises: 0003_identity_optional_fields
Create Date: 2026-05-14
"""

from alembic import op


revision = "0004_remove_platform_table"
down_revision = "0003_identity_optional_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")

    op.execute(
        """
        CREATE TABLE tasks_new (
            id UUID NOT NULL PRIMARY KEY,
            name VARCHAR(256) NOT NULL,
            platform_id UUID NOT NULL,
            type VARCHAR(7) NOT NULL,
            status VARCHAR(9) NOT NULL,
            payload JSON NOT NULL,
            schedule JSON NOT NULL,
            concurrency INTEGER NOT NULL,
            sync_mode VARCHAR(11) NOT NULL,
            success_criteria JSON NOT NULL,
            result_count INTEGER NOT NULL,
            error_count INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            started_at DATETIME NULL,
            completed_at DATETIME NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO tasks_new (
            id, name, platform_id, type, status, payload, schedule, concurrency, sync_mode,
            success_criteria, result_count, error_count, created_at, started_at, completed_at
        )
        SELECT
            id, name, platform_id, type, status, payload, schedule, concurrency, sync_mode,
            success_criteria, result_count, error_count, created_at, started_at, completed_at
        FROM tasks
        """
    )
    op.execute("DROP TABLE tasks")
    op.execute("ALTER TABLE tasks_new RENAME TO tasks")

    op.execute(
        """
        CREATE TABLE bots_new (
            id NUMERIC NOT NULL PRIMARY KEY,
            name VARCHAR(256) NOT NULL,
            platform_id NUMERIC NOT NULL,
            identity_id NUMERIC NULL,
            proxy_id NUMERIC NULL,
            skeleton VARCHAR(128) NOT NULL,
            mode VARCHAR(11) NOT NULL,
            status VARCHAR(7) NOT NULL,
            communication_mode VARCHAR(15) NOT NULL,
            behaviour_pattern VARCHAR(10) NOT NULL,
            parameters JSON NOT NULL,
            algorithm_config JSON NOT NULL,
            task_id NUMERIC NULL,
            flag_count INTEGER NOT NULL,
            last_active DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            password VARCHAR(256) NULL,
            identity VARCHAR(256) NULL,
            profile_name VARCHAR(256) NULL,
            profile_password VARCHAR(256) NULL,
            platform_name VARCHAR(128) NULL,
            is_healthy BOOLEAN DEFAULT 1 NOT NULL,
            sandbox_ids JSON DEFAULT '[]' NOT NULL,
            state VARCHAR(32) DEFAULT 'not_active' NOT NULL,
            FOREIGN KEY(identity_id) REFERENCES identities (id),
            FOREIGN KEY(proxy_id) REFERENCES proxies (id),
            FOREIGN KEY(task_id) REFERENCES tasks (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO bots_new (
            id, name, platform_id, identity_id, proxy_id, skeleton, mode, status,
            communication_mode, behaviour_pattern, parameters, algorithm_config, task_id,
            flag_count, last_active, created_at, updated_at, password, identity, profile_name,
            profile_password, platform_name, is_healthy, sandbox_ids, state
        )
        SELECT
            id, name, platform_id, identity_id, proxy_id, skeleton, mode, status,
            communication_mode, behaviour_pattern, parameters, algorithm_config, task_id,
            flag_count, last_active, created_at, updated_at, password, identity, profile_name,
            profile_password, platform_name, is_healthy, sandbox_ids, state
        FROM bots
        """
    )
    op.execute("DROP TABLE bots")
    op.execute("ALTER TABLE bots_new RENAME TO bots")

    op.execute("DROP TABLE IF EXISTS platforms")
    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    pass
