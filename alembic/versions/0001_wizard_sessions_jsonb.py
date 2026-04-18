from __future__ import annotations

from alembic import op

revision = "0001_wizard_sessions_jsonb"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Делаем migration максимально "мягким" для неизвестной текущей схемы:
    # - создаём таблицы, если их нет
    # - если wizard_sessions.data уже существует, приводим тип к JSONB
    op.execute(
        """
DO $$
BEGIN
    -- users
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name='users'
    ) THEN
        CREATE TABLE public.users (
            id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            full_name VARCHAR(255) NOT NULL,
            business_type VARCHAR(10),
            has_okved_5229 BOOLEAN,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    END IF;

    -- wizard_sessions
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name='wizard_sessions'
    ) THEN
        CREATE TABLE public.wizard_sessions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            step VARCHAR(50) NOT NULL DEFAULT 'waiting_for_inn',
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS wizard_sessions_user_id_idx ON public.wizard_sessions (user_id);
    ELSE
        -- Приводим step к корректному дефолту
        ALTER TABLE public.wizard_sessions
            ALTER COLUMN step SET DEFAULT 'waiting_for_inn';

        -- Приводим data к JSONB (если колонка data есть)
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='wizard_sessions'
              AND column_name='data'
        ) THEN
            BEGIN
                ALTER TABLE public.wizard_sessions
                    ALTER COLUMN data TYPE JSONB
                    USING
                        CASE
                            WHEN data IS NULL OR data::text = '' THEN '{}'::jsonb
                            ELSE data::jsonb
                        END;
            EXCEPTION WHEN others THEN
                -- Если приведение не удалось (например, data уже в несоответствующем типе),
                -- оставляем как есть, чтобы не ломать прод рантайм.
                NULL;
            END;

            ALTER TABLE public.wizard_sessions
                ALTER COLUMN data SET DEFAULT '{}'::jsonb;

            ALTER TABLE public.wizard_sessions
                ALTER COLUMN data SET NOT NULL;
        END IF;

        -- Индекс на user_id (если отсутствует)
        IF NOT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='wizard_sessions_user_id_idx'
        ) THEN
            CREATE INDEX wizard_sessions_user_id_idx ON public.wizard_sessions (user_id);
        END IF;
    END IF;
END
$$;
        """
    )


def downgrade() -> None:
    # Негативный downgrade не делаем: преобразование JSONB обратно в текст/другой тип
    # может потерять данные и усложнит поддержку.
    # При необходимости откат делается отдельной миграцией.
    pass

