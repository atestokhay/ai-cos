from alembic import context
from sqlalchemy import create_engine, pool

from core.foundation.config import DatabaseSettings
from core.foundation.database import build_database_url

# No schema is defined yet, so autogenerate has nothing to compare against.
target_metadata = None


def run_migrations_online() -> None:
    engine = create_engine(build_database_url(DatabaseSettings()), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported")

run_migrations_online()
