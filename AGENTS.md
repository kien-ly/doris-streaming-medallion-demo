# Repository Guidelines

## Project Structure & Module Organization

- `docker-compose.yml` orchestrates Docker services: Redpanda, Doris FE/BE, MinIO, producer, dbt runner, and optional jobs.
- `sql/` holds Doris bootstrap scripts (databases, ODS tables, routine load, checkpoints, optional Iceberg notes).
- `dbt/` contains the dbt project, macros, models, tests, and compiled artifacts. `jobs/optional_iceberg_sink.py` plus `jobs/requirements.txt` implement the local Iceberg sink.
- `producer/` is the event generator (code + schemas). `doc/` stores the specification, validation report, and implementation-ready guidance.
- `README.md`, `.env.example`, `.gitignore`, and `AGENTS.md` are entry-point documentation.

## Build, Test, and Development Commands

- `docker compose up -d` boots the full stack in `demo-net`.
- `docker compose exec dbt-runner dbt run` builds bronze/silver/gold models after running `profiles.yml`.
- `docker compose exec dbt-runner dbt test` runs the declared schema tests; expect the two silver tests to warn but verify manually if needed.
- `docker compose exec jobs python optional_iceberg_sink.py` runs the optional sink (enable with `ICEBERG_ENABLED=true`).
- `docker compose logs <service>` or `docker compose ps` for live diagnostics.

## Coding Style & Naming Conventions

- Python files follow 4-space indentation and rely on `pyarrow`/`pyiceberg` naming for schema fields; keep logging messages direct and lower-case `snake_case` for helpers.
- dbt models use lower_snake_case names matching Doris schemas (`dwh.bronze_events`, `analytics.gold_*`). Schema tests and docs metadata are centralized in `dbt/models/schema.yml`; keep column names explicit and synchronized with model SQL.
- Documentation uses Markdown with relative links (`./path`). Keep sentences short and reference actual files or commands.

## Testing Guidelines

- Testing is manual via dbt: no automated framework beyond `dbt test`. Run `docker compose exec dbt-runner dbt run` before tests to ensure models exist.
- Use descriptive names for temporary validation scripts (e.g., `jobs/optional_iceberg_sink.py` already documents checkpoints); avoid modifying `dbt/target`.
- No additional coverage requirements beyond checking test outcomes and inspect `doc/validation-report.md` for expected counts.

## Commit & Pull Request Guidelines

- Follow `feat|fix|chore` prefixes in commit messages (e.g., `feat: build doris medallion demo`).
- PRs should include a concise description, `README.md` update when behavior changes, and a note about manual verification steps (Docker Compose status, dbt run/test) plus links to relevant docs.

## Agent-Specific Instructions

- Avoid pushing large binaries; Docker volumes (`minio-data`, `doris-*`) are excluded via `.gitignore`.
- Document any manual validation in `doc/validation-report.md` and keep `README.md` aligned with what has actually been run locally.
