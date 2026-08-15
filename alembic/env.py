import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# alembic.ini の logging 設定を読み込む
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# モデルの Base.metadata を渡す（autogenerate に必要）
from app.db.base import Base
import app.db.models  # noqa: F401 – モデルを Base に登録するための import

target_metadata = Base.metadata


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL が環境変数に設定されていません")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
