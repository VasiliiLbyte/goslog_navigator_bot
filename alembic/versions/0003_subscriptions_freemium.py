"""Модуль 4: подписки freemium + платежные поля.

Revision ID: 0003_subscriptions_freemium
Revises: 0002_counterparty_alerts
"""

from __future__ import annotations

from alembic import op

revision = "0003_subscriptions_freemium"
down_revision = "0002_counterparty_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='subscriptions'
    ) THEN
        CREATE TABLE public.subscriptions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            tier VARCHAR(20) NOT NULL DEFAULT 'free',
            starts_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            payment_id VARCHAR(128),
            CONSTRAINT fk_subscriptions_user
                FOREIGN KEY (user_id)
                REFERENCES public.users(id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id
            ON public.subscriptions (user_id);
    END IF;
END
$$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.subscriptions;")
