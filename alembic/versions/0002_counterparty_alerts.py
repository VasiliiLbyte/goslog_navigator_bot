"""Модуль 3: контрагенты + флаги утренних алертов.

Revision ID: 0002_counterparty_alerts
Revises: 0001_wizard_sessions_jsonb
"""

from __future__ import annotations

from alembic import op

revision = "0002_counterparty_alerts"
down_revision = "0001_wizard_sessions_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='users'
    ) THEN
        ALTER TABLE public.users
            ADD COLUMN IF NOT EXISTS daily_alerts_enabled BOOLEAN NOT NULL DEFAULT false;
        ALTER TABLE public.users
            ADD COLUMN IF NOT EXISTS own_inn_for_alerts VARCHAR(12);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='counterparties'
    ) THEN
        CREATE TABLE public.counterparties (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            inn VARCHAR(12) NOT NULL,
            display_name VARCHAR(512),
            okved_main VARCHAR(128),
            okved_extra TEXT,
            status_text VARCHAR(255),
            reg_date VARCHAR(32),
            in_goslog_registry BOOLEAN,
            goslog_check_note VARCHAR(500),
            needs_attention BOOLEAN NOT NULL DEFAULT false,
            raw_ofdata JSONB,
            last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_counterparties_user_inn UNIQUE (user_id, inn)
        );
        CREATE INDEX IF NOT EXISTS ix_counterparties_user_id
            ON public.counterparties (user_id);
        CREATE INDEX IF NOT EXISTS ix_counterparties_inn
            ON public.counterparties (inn);
    END IF;
END
$$;
        """
    )


def downgrade() -> None:
    # Откат без потери users-колонок: только удаление таблицы контрагентов.
    op.execute(
        """
        DROP TABLE IF EXISTS public.counterparties;
        """
    )
