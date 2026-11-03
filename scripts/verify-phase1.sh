#!/usr/bin/env bash
# Phase 1 acceptance test. Runs only in the isolated aicos-acceptance Compose project,
# with throwaway secrets. It never starts the Docker daemon and never reads .env.
#
# Exit status: 0 all PASS, 1 any FAIL, 2 no FAIL but something NOT VERIFIED.
# The report (no secrets) is also written to .tools/verify-phase1-last.log.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly ROOT
readonly PROJECT="aicos-acceptance"
readonly API_PORT=18000
readonly BASE_URL="http://127.0.0.1:${API_PORT}"
readonly PROD_CONTAINER="${PROJECT}-prod-check"
readonly PROBE_TABLE="acceptance_persistence_probe"
readonly PGDATA_VOLUME="${PROJECT}_pgdata"

cd "$ROOT" || exit 1
mkdir -p .tools
exec > >(tee .tools/verify-phase1-last.log) 2>&1

# Nothing in the caller's environment may steer the project or override secrets.
unset COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES COMPOSE_ENV_FILES
unset POSTGRES_PASSWORD MIGRATOR_DB_PASSWORD APP_DB_PASSWORD APP_ENV LOG_LEVEL

# --- Result tracking --------------------------------------------------------

ALL_IDS=(A1 A2 A3 A4 A5 A6 A6-only-acceptance A7 A8 A9
         S1 S1a S1b S1c S1d S1e S2 S3 S4 S5 S6 S7 S8 S9-host S9-images S10 S11
         S12 S12-lan S13 S14 S15 I1 I2 I3 I4 I5)
declare -A RESULT NOTE
for id in "${ALL_IDS[@]}"; do RESULT[$id]="NOT VERIFIED"; NOTE[$id]=""; done

record() { # id PASS|FAIL|NOT VERIFIED [note]; a FAIL is never overwritten
    local id=$1 status=$2 note=${3:-}
    [ "${RESULT[$id]}" = "FAIL" ] && return 0
    RESULT[$id]=$status
    NOTE[$id]=$note
    echo "  [$status] $id${note:+ - $note}"
}
check() { # id note command...
    local id=$1 note=$2
    shift 2
    if "$@"; then record "$id" PASS "$note"; else record "$id" FAIL "$note"; fi
}
precheck() { # id note command...; only a failure is final, a pass still needs Docker
    local id=$1 note=$2
    shift 2
    if "$@"; then echo "  [ok] $id precheck - $note"; else record "$id" FAIL "$note"; fi
}
section() { printf '\n=== %s ===\n' "$1"; }

print_report() {
    section "RESULTS"
    local failed=0 unverified=0 id
    for id in "${ALL_IDS[@]}"; do
        printf '%-14s %-20s %s\n' "${RESULT[$id]}" "$id" "${NOTE[$id]}"
        case "${RESULT[$id]}" in
            FAIL) failed=$((failed + 1)) ;;
            "NOT VERIFIED") unverified=$((unverified + 1)) ;;
        esac
    done
    printf '\nFAIL: %d  NOT VERIFIED: %d  TOTAL: %d\n' "$failed" "$unverified" "${#ALL_IDS[@]}"
    if [ "$failed" -gt 0 ]; then EXIT_CODE=1
    elif [ "$unverified" -gt 0 ]; then EXIT_CODE=2
    else EXIT_CODE=0; fi
}

# --- Host checks (need no container) ----------------------------------------

section "Host checks"

if [ -x .venv/bin/pytest ]; then
    if .venv/bin/pytest -q tests/unit >/dev/null 2>&1; then
        record A9 PASS "unit test suite"
        record A7 PASS "unit tests; container part follows"
    else
        record A9 FAIL "unit test suite"
        record A7 FAIL "unit tests"
    fi
    import_contracts_hold() { .venv/bin/lint-imports --no-cache >/dev/null 2>&1; }
    check S8 "contracts kept" import_contracts_hold
    check S13 "see check_licenses.py output" .venv/bin/python scripts/check_licenses.py
else
    record A9 "NOT VERIFIED" ".venv missing"
fi

check S9-host "pattern-based, see check_secrets.sh" scripts/check_secrets.sh

static_image_tags_ok() {
    grep -q '^FROM python:3\.12\.16-slim-trixie AS base$' Dockerfile \
        && grep -q 'image: postgres:18\.6-trixie$' compose.yaml \
        && ! grep -nE '(:latest\b|image: *[^ ]*\*|^FROM [^ ]*\*)' Dockerfile compose.yaml
}
check S15 "exact image tags" static_image_tags_ok

probe_table_only_in_script() {
    ! grep -rq "$PROBE_TABLE" migrations apps core docker
}
precheck A6-only-acceptance "table name absent from migrations, code and init" probe_table_only_in_script

# Built from parts so this check does not match its own source line.
forbidden_cleanup_commands() {
    local volume_rm="volume r""m" volume_prune="volume pru""ne" system_prune="system pru""ne"
    ! grep -qE "($volume_rm|$volume_prune|$system_prune)" "$0"
}
precheck I5 "no broad cleanup command in script" forbidden_cleanup_commands

compose_has_no_fixed_names() {
    ! grep -qE '^\s*container_name:' compose.yaml \
        && ! sed -n '/^volumes:/,/^networks:/p' compose.yaml | grep -qE '^\s+name:'
}
precheck I3 "no fixed container or volume name" compose_has_no_fixed_names

daemon_autostart_disabled() {
    local unit state
    for unit in docker.service docker.socket containerd.service; do
        state=$(systemctl is-enabled "$unit" 2>/dev/null)
        [ "$state" = "disabled" ] || { echo "  $unit: ${state:-absent}"; return 1; }
    done
    ! id -nG | tr ' ' '\n' | grep -qx docker
}
if command -v docker >/dev/null 2>&1; then
    check S14 "units disabled, user not in docker group" daemon_autostart_disabled
fi

# --- Docker preflight -------------------------------------------------------

section "Docker preflight"

D=()
if ! command -v docker >/dev/null 2>&1; then
    NOT_READY="Docker is not installed"
elif docker info >/dev/null 2>&1; then
    D=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
    D=(sudo -n docker)
elif [ -t 0 ] && sudo docker info >/dev/null 2>&1; then
    D=(sudo docker)
else
    NOT_READY="Docker daemon is not reachable (stopped, or sudo needs a terminal). Start it with: sudo systemctl start docker.service"
fi

if [ "${#D[@]}" -eq 0 ]; then
    echo "$NOT_READY"
    print_report
    exit "$EXIT_CODE"
fi
echo "Using: ${D[*]}"

# --- Throwaway secrets, isolated from .env ----------------------------------

WORK_DIR=$(mktemp -d)
chmod 700 "$WORK_DIR"
ENV_FILE="$WORK_DIR/acceptance.env"
PROD_ENV_FILE="$WORK_DIR/prod.env"
SECRETS_FILE="$WORK_DIR/secrets"

new_secret() { python3 -c 'import secrets; print(secrets.token_hex(32))'; }
PG_SECRET=$(new_secret)
MIGRATOR_SECRET=$(new_secret)
APP_SECRET=$(new_secret)
TOKEN=$(new_secret)

(
    umask 077
    printf 'POSTGRES_PASSWORD=%s\nMIGRATOR_DB_PASSWORD=%s\nAPP_DB_PASSWORD=%s\n' \
        "$PG_SECRET" "$MIGRATOR_SECRET" "$APP_SECRET" >"$ENV_FILE"
    printf 'APP_ENV=development\nLOG_LEVEL=INFO\nAPI_PORT=%s\n' "$API_PORT" >>"$ENV_FILE"
    printf 'APP_ENV=production\nDB_HOST=db\nDB_PORT=5432\nDB_NAME=aicos\nDB_USER=app\nDB_PASSWORD=%s\n' \
        "$APP_SECRET" >"$PROD_ENV_FILE"
    printf '%s\n%s\n%s\n' "$PG_SECRET" "$MIGRATOR_SECRET" "$APP_SECRET" >"$SECRETS_FILE"
)

C=("${D[@]}" compose -p "$PROJECT" --env-file "$ENV_FILE" -f "$ROOT/compose.yaml" --project-directory "$ROOT")

check I2 "0600 temp env file, passed with --env-file" \
    test "$(stat -c '%a' "$ENV_FILE")" = "600"

cleanup_done=0
cleanup() {
    [ "$cleanup_done" = 1 ] && return 0
    cleanup_done=1
    section "Cleanup (project ${PROJECT} only)"
    "${D[@]}" rm -f "$PROD_CONTAINER" >/dev/null 2>&1
    "${C[@]}" down -v --remove-orphans --rmi local >/dev/null 2>&1
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

# Other volumes and dev containers are fingerprinted to prove they stay untouched.
snapshot_others() {
    local name
    "${D[@]}" volume ls -q | grep -v "^${PROJECT}_" | sort | while read -r name; do
        "${D[@]}" volume inspect -f '{{.Name}} {{.CreatedAt}} {{.Mountpoint}}' "$name"
    done
    "${D[@]}" ps -a --no-trunc --filter label=com.docker.compose.project=aicos-dev \
        --format '{{.ID}} {{.CreatedAt}} {{.State}}' | sort
}

"${C[@]}" down -v --remove-orphans >/dev/null 2>&1
SNAPSHOT_BEFORE=$(snapshot_others)

# --- Helpers ----------------------------------------------------------------

without_secrets() { grep -vFf "$SECRETS_FILE"; }

http_status() { # url -> prints the status code, stores the body in HTTP_BODY_FILE
    curl -s -o "$HTTP_BODY_FILE" -w '%{http_code}' --max-time 8 "$1"
}
HTTP_BODY_FILE="$WORK_DIR/body"

wait_for_status() { # url expected-status timeout-seconds
    local deadline=$((SECONDS + $3))
    while [ "$SECONDS" -lt "$deadline" ]; do
        [ "$(http_status "$1")" = "$2" ] && return 0
        sleep 1
    done
    return 1
}

container_id() { "${C[@]}" ps -aq "$1"; }

wait_for_healthy() { # service timeout-seconds
    local deadline=$((SECONDS + $2)) cid
    while [ "$SECONDS" -lt "$deadline" ]; do
        cid=$(container_id "$1")
        [ -n "$cid" ] && [ "$("${D[@]}" inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null)" = "healthy" ] && return 0
        sleep 1
    done
    return 1
}

psql_as() { # role, with SQL on stdin. Authenticates over TCP with the role's password.
    local role=$1 variable
    case "$role" in
        app) variable=APP_DB_PASSWORD ;;
        migrator) variable=MIGRATOR_DB_PASSWORD ;;
        *) return 99 ;;
    esac
    "${C[@]}" exec -T db sh -c \
        "PGPASSWORD=\"\$$variable\" exec psql -h 127.0.0.1 -U $role -d aicos -X -At -v ON_ERROR_STOP=1"
}

denied_with_42501() { # role sql
    # Captured first: psql exits non-zero on the expected error, which pipefail would report.
    local output
    output=$(printf '\\set VERBOSITY sqlstate\n%s\n' "$2" | psql_as "$1" 2>&1)
    grep -q 'ERROR:  42501' <<<"$output"
}

contains_secret() { grep -qFf "$SECRETS_FILE" <<<"$1"; }

in_api_pytest() { # pytest selection arguments
    "${C[@]}" exec -T api pytest -q -p no:cacheprovider "$@" >"$WORK_DIR/pytest.out" 2>&1
    local rc=$?
    [ "$rc" -eq 0 ] || without_secrets <"$WORK_DIR/pytest.out" | tail -30
    return "$rc"
}

# --- Start ------------------------------------------------------------------

section "Start stack"
if ! "${C[@]}" up -d --build --wait --wait-timeout 240; then
    record A1 FAIL "compose up failed"
    "${C[@]}" logs --no-color 2>&1 | without_secrets | tail -60
    cleanup
    print_report
    exit "$EXIT_CODE"
fi

API_CID=$(container_id api)
MIGRATE_CID=$(container_id migrate)
RUNTIME_IMAGE=$("${D[@]}" inspect -f '{{.Config.Image}}' "$MIGRATE_CID")
DEV_IMAGE=$("${D[@]}" inspect -f '{{.Config.Image}}' "$API_CID")

api_is_live() {
    [ "$("${D[@]}" inspect -f '{{.State.Health.Status}}' "$API_CID")" = "healthy" ] \
        && [ "$(http_status "$BASE_URL/health/live")" = "200" ]
}
check A1 "api healthy, /health/live 200" api_is_live

start_order_ok() {
    local exit_code finished started
    exit_code=$("${D[@]}" inspect -f '{{.State.ExitCode}}' "$MIGRATE_CID")
    finished=$("${D[@]}" inspect -f '{{.State.FinishedAt}}' "$MIGRATE_CID")
    started=$("${D[@]}" inspect -f '{{.State.StartedAt}}' "$API_CID")
    [ "$exit_code" = "0" ] && ! [[ "${started:0:19}" < "${finished:0:19}" ]]
}
check A5 "migrate exit 0 before api start" start_order_ok

project_label_ok() {
    [ "$("${D[@]}" inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$API_CID")" = "$PROJECT" ]
}
check I1 "container belongs to ${PROJECT}" project_label_ok
project_volume_exists() { "${D[@]}" volume inspect "$PGDATA_VOLUME" >/dev/null 2>&1; }
check I3 "volume is ${PGDATA_VOLUME}, API on port ${API_PORT}" project_volume_exists

# --- Database connection and privileges -------------------------------------

section "Database privileges (app role, real statements)"
check A2 "connected as app" in_api_pytest tests/integration/test_db_connection.py
P=tests/integration/test_db_privileges.py
check S1 "DDL denied with SQLSTATE 42501" in_api_pytest "$P" -k test_statement_is_denied
check S1b "effective privileges absent" in_api_pytest "$P" -k test_effective_privilege
check S1c "no PUBLIC ACL entries, ACLs not NULL" in_api_pytest "$P" -k test_public_has_no
check S1d "cannot connect to other databases" in_api_pytest "$P" -k test_app_cannot_connect
check S1e "no memberships, wrong password rejected" in_api_pytest "$P" -k "test_app_is_not_a_member or test_wrong_password"
check S2 "app has no elevated attribute" in_api_pytest "$P" -k "test_role_has_no_elevated and app"
check S3 "migrator has no elevated attribute" in_api_pytest "$P" -k "test_role_has_no_elevated and migrator"

migrator_can_do_ddl() {
    psql_as migrator >/dev/null 2>&1 <<'SQL'
CREATE TABLE s1a_probe (id integer);
DROP TABLE s1a_probe;
CREATE SCHEMA s1a_probe;
DROP SCHEMA s1a_probe;
SQL
}
check S1a "same DDL succeeds for migrator" migrator_can_do_ddl

echo "  Deliberately retained PUBLIC defaults for app:"
psql_as app <<'SQL' | sed 's/^/    /'
SELECT 'pg_catalog schema USAGE: ' || has_schema_privilege('app', 'pg_catalog', 'USAGE');
SELECT 'plpgsql language USAGE: ' || has_language_privilege('app', 'plpgsql', 'USAGE');
SELECT 'functions executable: ' || count(*) FROM pg_proc WHERE has_function_privilege('app', oid, 'EXECUTE');
SQL

# --- Environment ------------------------------------------------------------

section "Environment"

settings_loaded() {
    local loaded
    loaded=$("${C[@]}" exec -T api python -c \
        'from core.foundation.config import ApiSettings, DatabaseSettings as D; d = D(); print(ApiSettings().app_env.value, d.db_user, d.db_host)')
    [ "$loaded" = "development app db" ]
}
missing_env_fails_without_secret() {
    local output rc
    output=$("${C[@]}" run --rm --no-deps -T -e APP_ENV= api python -c \
        'from apps.api.main import create_app; create_app()' 2>&1)
    rc=$?
    [ "$rc" -ne 0 ] && ! grep -qFf "$SECRETS_FILE" <<<"$output"
}
check A7 "container loads expected values" settings_loaded
check A7 "invalid env fails fast, no secret in error" missing_env_fails_without_secret

env_excludes() { # env-text name-regex secret...
    local text=$1 names=$2
    shift 2
    grep -qE "^($names)=" <<<"$text" && return 1
    local secret
    for secret in "$@"; do
        grep -qF "$secret" <<<"$text" && return 1
    done
    return 0
}
api_env_clean() {
    local runtime configured
    runtime=$("${C[@]}" exec -T api env)
    configured=$("${D[@]}" inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$API_CID")
    env_excludes "$runtime" 'POSTGRES_PASSWORD|MIGRATOR_DB_PASSWORD' "$PG_SECRET" "$MIGRATOR_SECRET" \
        && env_excludes "$configured" 'POSTGRES_PASSWORD|MIGRATOR_DB_PASSWORD' "$PG_SECRET" "$MIGRATOR_SECRET"
}
migrate_env_clean() {
    env_excludes "$("${C[@]}" run --rm --no-deps -T migrate env)" \
        'POSTGRES_PASSWORD|APP_DB_PASSWORD' "$PG_SECRET" "$APP_SECRET"
}
check S4 "no postgres or migrator credential in api" api_env_clean
check S5 "no postgres or app credential in migrate" migrate_env_clean

# --- Migrations -------------------------------------------------------------

section "Migrations"

alembic() { "${C[@]}" run --rm --no-deps -T migrate alembic "$@"; }
current_revision() { alembic current 2>/dev/null; }
migration_cycle() {
    alembic upgrade head >/dev/null 2>&1 \
        && [[ "$(current_revision)" == "0001 (head)"* ]] \
        && alembic downgrade base >/dev/null 2>&1 \
        && [[ "$(current_revision)" != *0001* ]] \
        && alembic upgrade head >/dev/null 2>&1 \
        && [[ "$(current_revision)" == "0001 (head)"* ]]
}
check A4 "upgrade, current, downgrade, upgrade" migration_cycle

# --- Health check against a real outage -------------------------------------

section "Database outage"

readiness_cycle() {
    wait_for_status "$BASE_URL/health/ready" 200 30 || return 1
    "${C[@]}" stop db >/dev/null 2>&1 || return 1
    wait_for_status "$BASE_URL/health/ready" 503 45 || return 1
    grep -qx '{"status":"unavailable"}' "$HTTP_BODY_FILE" \
        && record S10 PASS 'body is exactly {"status":"unavailable"}' \
        || record S10 FAIL "unexpected 503 body"
    [ "$(http_status "$BASE_URL/health/live")" = "200" ] || return 1
    "${C[@]}" start db >/dev/null 2>&1 || return 1
    wait_for_status "$BASE_URL/health/ready" 200 60
}
check A3 "ready 200, db down 503, db back 200" readiness_cycle

logs_have_no_secret() {
    local logs
    logs=$("${C[@]}" logs --no-color 2>&1) || return 1
    ! contains_secret "$logs"
}
check S11 "no password in any service log after outage" logs_have_no_secret

# --- Network surface --------------------------------------------------------

section "Network surface"

listens_on_all_interfaces_in_container() {
    "${C[@]}" exec -T api grep -qE '^ *[0-9]+: 00000000:1F40 00000000:0000 0A' /proc/net/tcp
}
publishes_only_on_loopback() {
    local host_ip published
    host_ip=$("${D[@]}" inspect -f '{{(index (index .HostConfig.PortBindings "8000/tcp") 0).HostIp}}' "$API_CID")
    published=$("${C[@]}" port api 8000)
    [ "$host_ip" = "127.0.0.1" ] && [ "$published" = "127.0.0.1:${API_PORT}" ] \
        && [ "$(http_status "$BASE_URL/health/live")" = "200" ]
}
db_not_published() {
    [ "$("${D[@]}" inspect -f '{{json .HostConfig.PortBindings}}' "$(container_id db)")" = "{}" ]
}
network_surface_ok() {
    listens_on_all_interfaces_in_container && publishes_only_on_loopback && db_not_published
}
check S12 "0.0.0.0:8000 in container, 127.0.0.1 on host, db unpublished" network_surface_ok

LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p')
if [ -z "$LAN_IP" ]; then
    record S12-lan "NOT VERIFIED" "no LAN address on this machine"
elif curl -s -o /dev/null --connect-timeout 3 --max-time 5 "http://${LAN_IP}:${API_PORT}/health/live"; then
    record S12-lan FAIL "API answered on the LAN address"
else
    record S12-lan PASS "API does not answer on the LAN address"
fi

# --- Persistence ------------------------------------------------------------

section "Persistence"

read_token_as_app() {
    [ "$(printf 'SELECT token FROM %s;\n' "$PROBE_TABLE" | psql_as app 2>/dev/null)" = "$TOKEN" ]
}
volume_identity() { "${D[@]}" volume inspect -f '{{.CreatedAt}} {{.Mountpoint}}' "$PGDATA_VOLUME"; }

persistence_scenario() {
    psql_as migrator >/dev/null 2>&1 <<SQL || { echo "  migrator could not create the table"; return 1; }
CREATE TABLE $PROBE_TABLE (token text NOT NULL);
GRANT SELECT, INSERT ON $PROBE_TABLE TO app;
SQL
    printf "INSERT INTO %s (token) VALUES ('%s');\n" "$PROBE_TABLE" "$TOKEN" | psql_as app >/dev/null 2>&1 \
        || { echo "  app could not insert"; return 1; }
    read_token_as_app || { echo "  app could not read back"; return 1; }
    denied_with_42501 app "DROP TABLE $PROBE_TABLE;" || { echo "  app DROP not denied"; return 1; }
    denied_with_42501 app "DELETE FROM $PROBE_TABLE;" || { echo "  app DELETE not denied"; return 1; }

    "${C[@]}" restart db >/dev/null 2>&1 && wait_for_healthy db 60 \
        && read_token_as_app || { echo "  token lost after restart"; return 1; }

    local before_id after_id before_volume
    before_id=$(container_id db)
    "${C[@]}" up -d --force-recreate --no-deps db >/dev/null 2>&1 && wait_for_healthy db 60 \
        || { echo "  recreate failed"; return 1; }
    after_id=$(container_id db)
    [ "$before_id" != "$after_id" ] || { echo "  container was not recreated"; return 1; }
    read_token_as_app || { echo "  token lost after force-recreate"; return 1; }

    before_id=$after_id
    before_volume=$(volume_identity)
    "${C[@]}" down >/dev/null 2>&1 || { echo "  down failed"; return 1; }
    [ -z "$(container_id db)" ] || { echo "  db container survived down"; return 1; }
    "${C[@]}" up -d --wait --wait-timeout 180 >/dev/null 2>&1 || { echo "  up after down failed"; return 1; }
    after_id=$(container_id db)
    [ "$before_id" != "$after_id" ] || { echo "  container id unchanged after down/up"; return 1; }
    [ "$before_volume" = "$(volume_identity)" ] || { echo "  volume changed"; return 1; }
    read_token_as_app || { echo "  token lost after down/up"; return 1; }
}
check A6 "written by app; survives restart, recreate and down/up" persistence_scenario
API_CID=$(container_id api)

# --- Compose lifecycle ------------------------------------------------------

section "Compose lifecycle"

stop_start_cycle() {
    "${C[@]}" stop >/dev/null 2>&1 || return 1
    [ -z "$("${C[@]}" ps -q --status running)" ] || return 1
    "${C[@]}" start >/dev/null 2>&1 || return 1
    wait_for_status "$BASE_URL/health/ready" 200 90
}
check A5 "stop leaves nothing running, start recovers; down/up covered by A6" stop_start_cycle

# --- Runtime image ----------------------------------------------------------

section "Runtime image"

run_in_runtime() { "${D[@]}" run --rm -i --entrypoint sh "$RUNTIME_IMAGE" -c "$1"; }

runtime_is_non_root() {
    [ "$(run_in_runtime 'id -u')" != "0" ]
}
runtime_has_no_dev_tools() {
    run_in_runtime 'if command -v uv pytest lint-imports >/dev/null 2>&1; then exit 1; fi
python - <<PY
import importlib.util, sys
sys.exit(any(importlib.util.find_spec(m) for m in ("pytest", "httpx", "importlinter", "uv")))
PY'
}
check S6 "image user is not root" runtime_is_non_root
check S7 "no pytest, httpx, import-linter or uv" runtime_has_no_dev_tools

production_mode() {
    "${D[@]}" run -d --name "$PROD_CONTAINER" --network "${PROJECT}_backend" \
        --env-file "$PROD_ENV_FILE" "$RUNTIME_IMAGE" >/dev/null || return 1
    local probe='
import sys, time, urllib.error, urllib.request
def status(path):
    try:
        return urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=3).status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return 0
deadline = time.time() + 30
while status("/health/ready") != 200 and time.time() < deadline:
    time.sleep(1)
ok = status("/health/ready") == 200 and all(status(p) == 404 for p in ("/docs", "/redoc", "/openapi.json"))
sys.exit(0 if ok else 1)
'
    "${D[@]}" exec "$PROD_CONTAINER" python -c "$probe" || return 1
    [ "$("${D[@]}" exec "$PROD_CONTAINER" id -u)" != "0" ] || return 1
    "${D[@]}" rm -f "$PROD_CONTAINER" >/dev/null
    # Debug must be refused outright in production.
    if "${D[@]}" run --rm --network none --env-file "$PROD_ENV_FILE" -e APP_DEBUG=true \
        "$RUNTIME_IMAGE" python -c 'from apps.api.main import create_app; create_app()' >/dev/null 2>&1; then
        return 1
    fi
    # Development keeps the docs available.
    [ "$(http_status "$BASE_URL/docs")" = "200" ]
}
check A8 "runtime image in production: docs 404, debug refused; dev docs 200" production_mode

# --- Secrets in images ------------------------------------------------------

section "Secrets in images"

image_is_clean() { # image
    local image=$1 metadata
    metadata=$("${D[@]}" history --no-trunc "$image" 2>&1) || return 1
    contains_secret "$metadata" && return 1
    metadata=$("${D[@]}" inspect "$image" 2>&1) || return 1
    contains_secret "$metadata" && return 1
    "${D[@]}" run --rm -i --entrypoint sh "$image" -c \
        'cat >/tmp/needles; test ! -e /app/.env && ! grep -rqFf /tmp/needles /app --exclude-dir=.venv' \
        <"$SECRETS_FILE"
}
repository_is_clean() {
    ! grep -rqFf "$SECRETS_FILE" "$ROOT" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.tools
}
images_clean() { image_is_clean "$RUNTIME_IMAGE" && image_is_clean "$DEV_IMAGE" && repository_is_clean; }
check S9-images "no test password or .env in images or repository" images_clean

# --- Cleanup and isolation proof --------------------------------------------

cleanup
trap - EXIT INT TERM

section "Isolation"

if "${D[@]}" volume inspect "$PGDATA_VOLUME" >/dev/null 2>&1; then
    record A6-only-acceptance FAIL "acceptance volume survived cleanup"
    record I5 FAIL "acceptance volume survived cleanup"
else
    record A6-only-acceptance PASS "table name absent from code; acceptance volume deleted"
    record I5 PASS "only the acceptance project was removed"
fi

if [ "$SNAPSHOT_BEFORE" != "$(snapshot_others)" ]; then
    record I4 FAIL "another volume or dev container changed"
elif ! grep -q '^aicos-dev_pgdata ' <<<"$SNAPSHOT_BEFORE"; then
    record I4 "NOT VERIFIED" "no aicos-dev_pgdata volume existed to compare"
else
    record I4 PASS "aicos-dev_pgdata and other resources unchanged ($(grep -c . <<<"$SNAPSHOT_BEFORE") entries)"
fi

print_report
exit "$EXIT_CODE"
