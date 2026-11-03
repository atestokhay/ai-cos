# Project Guidelines & Operational Rules

## 1. Core Rules (Token Optimization)

- **Be concise:** Skip greetings, filler, routine summaries, and post-explanations. Return the requested solution, code, or decision directly.
- **Targeted reading:** Do not scan entire large files or directories by default. Read only relevant files, sections, line ranges, or functions. Expand the scope only when the task requires it.
- **Documentation first:** Before making architectural, data-model, business-rule, security, or API decisions, consult the relevant reference in `docs/`.
- **No invented requirements:** Treat `docs/` as the technical source of truth. Do not present unspecified behavior, schemas, routes, error formats, or policies as settled decisions. Identify gaps and conflicts explicitly.
- **Plan before complex work:** For multi-file changes, architectural work, or tasks with significant risk, use Plan Mode. Present a concise plan and wait for approval before editing.
- **Minimal context:** Do not reread documentation that is unrelated to the current task.

## 2. Reference Documentation

Read only the documents relevant to the task:

- `docs/architecture-and-requirements.md` — system architecture, components, roles, infrastructure, and requirements.
- `docs/data-model.md` — conceptual entities, relationships, state models, and unresolved data-model decisions.
- `docs/business-rules.md` — workflows, permissions, governance, approval rules, lifecycle rules, and operational constraints.
- `docs/api-spec.md` — API requirements and currently specified interface contracts.

If a decision spans multiple areas, consult each relevant document. Do not assume that a conceptual model is already a finalized database schema.

## 3. Code & Architecture Standards

- **Modularity:** Keep functions and modules focused, cohesive, and single-purpose.
- **Minimal edits:** Change only what the task requires. Do not reformat, rename, or restructure unrelated code.
- **Consistency:** Follow the existing project conventions unless the task explicitly changes them.
- **Error handling:** Follow `docs/api-spec.md` where behavior is specified. If the required error format or behavior is not defined, report the gap and propose an option; do not silently invent a project-wide standard.
- **Security and permissions:** Follow the security, authorization, approval, and isolation rules in `docs/business-rules.md` and the other relevant specifications. Do not weaken controls to make implementation easier.
- **Dependencies:** Do not add, upgrade, or remove dependencies without checking necessity, compatibility, maintenance status, and license implications.

## 4. Task Workflow

### Before implementation
1. Identify the task scope and inspect only the relevant code and documentation.
2. Check whether the requested behavior is already specified.
3. Identify missing requirements, contradictions, security implications, and affected modules.
4. For complex or multi-file work, enter Plan Mode and provide:
   - the implementation steps;
   - the files/modules expected to change;
   - the relevant documentation references;
   - tests and acceptance criteria;
   - unresolved decisions or risks.
5. Do not modify files until the plan is approved.

### During implementation
- Stay within the approved scope.
- Do not make unrelated improvements or speculative features.
- Keep changes small and reviewable.
- Add or update tests for changed behavior.
- Do not claim a test, build, or check passed unless it was actually run and its result was inspected.

### After implementation
- Run the relevant tests and checks.
- Report only the files changed, checks actually run, their results, and any remaining blockers.
- Do not commit or push unless explicitly instructed.

## 5. Common Workflows & Commands

Use only commands that exist in the current project. Inspect `package.json`, build configuration, or project scripts when necessary; do not assume every command below applies.

- **JavaScript/TypeScript build:** `npm run build`
- **C/C++ build:** `cmake -B build && cmake --build build`
- **Tests:** `npm test` (or the test command defined by the project)
- **Lint:** `npm run lint` (or the lint command defined by the project)

### Python (AI-COS)

The Docker daemon starts manually and the user is not in the `docker` group, so Docker commands need `sudo`. `uv` lives in the git-ignored `.tools/uv/` environment.

- **uv setup:** `python3 -m venv .tools/uv && .tools/uv/bin/pip install uv==0.13.6`
- **Install locked dependencies:** `.tools/uv/bin/uv sync --frozen`
- **Update the lock file:** `.tools/uv/bin/uv lock`
- **Python:** `.venv/bin/python` (3.12)
- **Unit tests:** `.venv/bin/pytest`
- **Import boundaries:** `.venv/bin/lint-imports --no-cache`
- **License and secret checks:** `.venv/bin/python scripts/check_licenses.py`, `scripts/check_secrets.sh`
- **Start Docker:** `sudo systemctl start docker.service`
- **Compose up/down:** `sudo docker compose up -d --build --wait`, `sudo docker compose down` (`down -v` permanently deletes the development database)
- **Integration tests:** `sudo docker compose exec -T api pytest -q -p no:cacheprovider tests/integration`
- **Alembic:** `sudo docker compose run --rm migrate alembic current`, `... alembic upgrade head`, `... alembic downgrade -1` (runs only in the `migrate` service)
- **Acceptance test:** `scripts/verify-phase1.sh` (isolated `aicos-acceptance` project; needs `sudo` access and a running daemon)

Do not run unrelated or expensive checks when a targeted check is sufficient. Run broader validation when the change affects shared infrastructure, security boundaries, or release-critical behavior.

## 6. Context Management

- Use `/compact` when the context becomes large or a feature/module is complete and the next task does not need the full conversation history.
- Before compacting, preserve essential implementation state: current task, decisions, changed files, test results, unresolved issues, and next step.
- Do not reread or restate the full project documentation after compaction; reopen only the references needed for the next task.

## 7. Git Rules

- Do not run `git commit`, `git push`, or destructive Git operations unless explicitly instructed.
- Do not discard, overwrite, or reset existing user changes.
- Before editing files with existing modifications, inspect the relevant diff and preserve unrelated work.
