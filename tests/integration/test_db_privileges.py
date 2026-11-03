"""Proves the app role's limits with real statements, not only catalog lookups."""

from collections.abc import Iterator

import psycopg
import pytest
from pydantic import SecretStr
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

from core.foundation.config import DatabaseSettings
from core.foundation.database import create_database_engine

INSUFFICIENT_PRIVILEGE = "42501"
PUBLIC_GRANTEE_OID = 0


@pytest.fixture
def connection() -> Iterator[Connection]:
    settings = DatabaseSettings()
    assert settings.db_user == "app"
    engine = create_database_engine(settings)
    with engine.connect() as conn:
        yield conn
        conn.rollback()
    engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE privilege_probe (id integer)",
        "CREATE SCHEMA privilege_probe",
        "CREATE TEMP TABLE privilege_probe (id integer)",
        "DROP TABLE alembic_version",
        "SELECT * FROM alembic_version",
    ],
)
def test_statement_is_denied_for_lack_of_privilege(
    connection: Connection, statement: str
) -> None:
    with pytest.raises(DBAPIError) as exc_info:
        connection.execute(text(statement))

    assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "check",
    [
        "has_database_privilege('app', 'aicos', 'CREATE')",
        "has_database_privilege('app', 'aicos', 'TEMPORARY')",
        "has_schema_privilege('app', 'public', 'CREATE')",
    ],
)
def test_effective_privilege_is_absent(connection: Connection, check: str) -> None:
    assert connection.execute(text(f"SELECT {check}")).scalar_one() is False


@pytest.mark.parametrize("database", ["aicos", "postgres", "template1"])
def test_public_has_no_database_acl_entry(connection: Connection, database: str) -> None:
    # A NULL datacl would mean PostgreSQL's defaults, which do include PUBLIC.
    has_acl, public_entries = connection.execute(
        text(
            "SELECT datacl IS NOT NULL, "
            "(SELECT count(*) FROM aclexplode(datacl) a WHERE a.grantee = :public) "
            "FROM pg_database WHERE datname = :database"
        ),
        {"public": PUBLIC_GRANTEE_OID, "database": database},
    ).one()

    assert has_acl is True
    assert public_entries == 0


def test_public_has_no_entry_on_public_schema(connection: Connection) -> None:
    has_acl, public_entries = connection.execute(
        text(
            "SELECT nspacl IS NOT NULL, "
            "(SELECT count(*) FROM aclexplode(nspacl) a WHERE a.grantee = :public) "
            "FROM pg_namespace WHERE nspname = 'public'"
        ),
        {"public": PUBLIC_GRANTEE_OID},
    ).one()

    assert has_acl is True
    assert public_entries == 0


@pytest.mark.parametrize("role", ["app", "migrator"])
def test_role_has_no_elevated_attributes(connection: Connection, role: str) -> None:
    attributes = connection.execute(
        text(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = :role"
        ),
        {"role": role},
    ).one()

    assert not any(attributes)


def test_app_is_not_a_member_of_any_role(connection: Connection) -> None:
    memberships = connection.execute(
        text(
            "SELECT count(*) FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'app'"
        )
    ).scalar_one()

    assert memberships == 0


@pytest.mark.parametrize("database", ["postgres", "template1"])
def test_app_cannot_connect_to_other_databases(database: str) -> None:
    settings = DatabaseSettings()

    with pytest.raises(psycopg.OperationalError) as exc_info:
        psycopg.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=database,
            user=settings.db_user,
            password=settings.db_password.get_secret_value(),
            connect_timeout=settings.db_connect_timeout_seconds,
        )

    # A failed connection carries no sqlstate in psycopg, so the server message is checked.
    assert f'permission denied for database "{database}"' in str(exc_info.value)


def test_wrong_password_is_rejected() -> None:
    settings = DatabaseSettings(db_password=SecretStr("definitely-not-the-password"))

    with pytest.raises(psycopg.OperationalError) as exc_info:
        psycopg.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password.get_secret_value(),
            connect_timeout=settings.db_connect_timeout_seconds,
        )

    assert f'password authentication failed for user "{settings.db_user}"' in str(exc_info.value)
