#!/usr/bin/env bash
# Pattern-based secret check of the working tree and Git history.
# This is not an exhaustive scanner: it finds common formats only.
# A line that is known not to hold a secret can carry the marker "secret-scan: allow".
# Exit status: 0 clean, 1 finding or misconfiguration.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

PATTERNS='-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b|\bsk-[A-Za-z0-9_-]{20,}\b|(PASSWORD|SECRET|TOKEN|API_KEY)[[:space:]]*[:=][[:space:]]*["'\'']?[A-Za-z0-9+/_-]{12,}'

status=0

if ! git check-ignore -q .env; then
    echo "FAIL: .env is not ignored by Git"
    status=1
fi

if [ -n "$(git ls-files -- .env)" ]; then
    echo "FAIL: .env is tracked by Git"
    status=1
fi

tree_hits=$(git ls-files -co --exclude-standard -z \
    | grep -zv '^scripts/check_secrets\.sh$' \
    | xargs -0 -r grep -nIE -- "$PATTERNS" 2>/dev/null \
    | grep -v 'secret-scan: allow')
if [ -n "$tree_hits" ]; then
    # Only the location is printed, so a real secret is not copied into logs.
    echo "FAIL: possible secret in working tree:"
    echo "$tree_hits" | cut -d: -f1,2
    status=1
else
    echo "OK: working tree has no pattern match"
fi

commits=$(git rev-list --all --count 2>/dev/null || echo 0)
if [ "$commits" -eq 0 ]; then
    echo "OK: Git history is empty (0 commits)"
elif git log -p --all -- . ':(exclude)scripts/check_secrets.sh' \
    | grep -E -- "$PATTERNS" | grep -qv 'secret-scan: allow'; then
    echo "FAIL: possible secret in Git history"
    status=1
else
    echo "OK: Git history has no pattern match ($commits commits)"
fi

exit "$status"
