#!/bin/sh
# Idempotent role-provisioning script. Runs as the postgres superuser on every
# compose-up (not just on empty volumes), ensuring the governance role exists
# before Alembic migrations attempt to GRANT privileges to it.
#
# Runs over the network; the postgres password is consumed from PGPASSWORD (never
# passed as a command-line argument).
set -eu

: "${POSTGRES_DB:?}"
: "${POSTGRES_PASSWORD:?}"
: "${GOVERNANCE_DB_PASSWORD:?}"

export PGPASSWORD="$POSTGRES_PASSWORD"

psql \
    --host=db \
    --username=postgres \
    --dbname="$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --no-psqlrc \
    <<'SQL'
\getenv governance_password GOVERNANCE_DB_PASSWORD

-- Check whether governance role already exists before attempting to create it.
SELECT NOT EXISTS (
    SELECT FROM pg_roles WHERE rolname = 'governance'
) AS needs_create \gset

\if :needs_create
CREATE ROLE governance
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'governance_password'; -- secret-scan: allow (psql variable)

GRANT CONNECT ON DATABASE aicos TO governance;
GRANT USAGE ON SCHEMA public TO governance;
\endif
SQL
