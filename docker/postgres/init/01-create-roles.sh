#!/bin/sh
# Runs once, as the bootstrap role, only when the data volume is empty.
# Passwords reach psql through \getenv, so they never appear in process arguments.
set -eu

: "${POSTGRES_DB:?}"
: "${MIGRATOR_DB_PASSWORD:?}"
: "${APP_DB_PASSWORD:?}"

psql --username postgres --dbname "$POSTGRES_DB" \
     --set ON_ERROR_STOP=1 --single-transaction --no-psqlrc <<'SQL'
\getenv migrator_password MIGRATOR_DB_PASSWORD
\getenv app_password APP_DB_PASSWORD

CREATE ROLE migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'migrator_password'; -- secret-scan: allow (psql variable)
CREATE ROLE app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'app_password'; -- secret-scan: allow (psql variable)

ALTER DATABASE aicos OWNER TO migrator;

-- Defaults inherited through PUBLIC: CONNECT and TEMPORARY on databases, schema access.
REVOKE ALL ON DATABASE aicos FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE postgres, template1 FROM PUBLIC;

-- Direct privileges of app, each removed explicitly.
REVOKE CREATE ON DATABASE aicos FROM app;
REVOKE TEMPORARY ON DATABASE aicos FROM app;
REVOKE CREATE ON SCHEMA public FROM app;

-- All that app receives here. Table privileges are granted by each migration.
GRANT CONNECT ON DATABASE aicos TO app;
GRANT USAGE ON SCHEMA public TO app;
SQL
