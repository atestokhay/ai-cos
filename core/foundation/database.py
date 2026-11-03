"""Engine construction. Connections are opened lazily, on first use."""

from sqlalchemy import URL, Engine, create_engine

from core.foundation.config import DatabaseSettings


def build_database_url(settings: DatabaseSettings) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


def create_database_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
        build_database_url(settings),
        pool_size=settings.db_pool_size,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )
