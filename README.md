# VYTALHouse Agent Platform

Production-ready MVP for a deterministic multi-agent market research and expansion workflow focused on the VYTAL COSMO CoOp — Maryland Fire + Ice concept.

## What is implemented

- FastAPI backend with:
  - token-gated API
  - input validation
  - rate limiting
  - structured JSON logging
  - persisted runs, tasks, outputs, evidence, artifacts, and seed knowledge
- Deterministic orchestrator with sub-agents:
  - OSINT Agent
  - CRE Agent
  - Compliance Agent
  - Strategy Agent
  - Content Discovery Agent
- Background worker:
  - embedded by default for local development
  - separate worker process supported via `docker-compose`
- Frontend dashboard for:
  - area input and run creation
  - agent/task status
  - outputs and evidence review
  - knowledge asset browsing
- Seed knowledge integration under `knowledge/seed`
- Guardrails:
  - planning-only disclaimers
  - claim-safety replacement for medical-style language
  - wellness/medical boundary reminders
- CI, Docker, docker-compose, and automated tests

## Architecture overview

### Runtime components

1. **Frontend dashboard**: server-hosted HTML/CSS/JS from `app/templates/index.html` and `app/static`.
2. **API service**: `app/main.py`.
3. **Worker service**: `app/worker.py`.
4. **Persistence layer**: SQLite by default via SQLAlchemy models in `app/models.py`.
5. **Seed knowledge loader**: `app/knowledge.py`.

### Task graph

The orchestrator creates a deterministic graph for each run:

1. `content_discovery`
2. `osint`
3. `cre`
4. `compliance`
5. `strategy` (depends on 1-4)
6. `executive_brief` (depends on 5)
7. `launch_roadmap` (depends on 5)
8. `launch_checklist` (depends on 5)

This graph supports retries, idempotent run creation via `idempotency_key`, and status auditing.

## What is intentionally deferred

- External OSINT/CRE/compliance provider integrations
- Multi-user auth/RBAC
- Redis/Postgres production deployment profiles
- PDF/Notion exports

The current implementation keeps those areas pluggable while delivering a fully working local production-style platform.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Default admin token: `local-admin-token-change-me`

## Local production-like run

```bash
docker compose up --build
```

This starts:
- API at `http://127.0.0.1:8000`
- Worker in a separate container

## Validation

```bash
ruff check .
pytest
python -m compileall app tests
```

## Example API flow

Create a run:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Authorization: ******" \
  -H "Content-Type: application/json" \
  -d '{
    "area": "Baltimore, Maryland",
    "notes": "Focus on premium wellness corridors",
    "idempotency_key": "baltimore-demo-1"
  }'
```

Process a run immediately:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/<RUN_ID>/process \
  -H "Authorization: ******"
```

Fetch run status:

```bash
curl http://127.0.0.1:8000/api/runs/<RUN_ID> \
  -H "Authorization: ******"
```

## UI usage flow

1. Enter the admin token.
2. Enter a target area and optional notes.
3. Start a run.
4. Refresh or process the run.
5. Review the task board, artifacts, and evidence panel.
6. Search seed knowledge and attach cited findings into your operator workflow.

## Test coverage

- Unit coverage for task graph creation and status transitions
- API coverage for run creation and auth enforcement
- Integration coverage for a sample run that produces artifacts and evidence