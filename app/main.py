from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import build_settings
from app.database import create_session_factory, init_db
from app.knowledge import search_knowledge_assets, seed_knowledge_assets
from app.logging_utils import configure_logging
from app.models import Run
from app.orchestration import create_run, process_run_until_complete, summarize_run_counts
from app.rate_limit import RateLimitMiddleware
from app.schemas import KnowledgeAssetRead, RunComparisonRead, RunCreateInput, RunRead, TaskRead
from app.security import require_admin_token
from app.worker import start_worker_thread


BASE_DIR = Path(__file__).resolve().parent


def get_session(request: Request):
    session_factory: sessionmaker = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def serialize_run(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        area=run.area,
        notes=run.notes,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        tasks=[
            TaskRead(
                id=task.id,
                kind=task.kind,
                title=task.title,
                agent_name=task.agent_name,
                status=task.status,
                attempt_count=task.attempt_count,
                max_attempts=task.max_attempts,
                last_error=task.last_error,
                created_at=task.created_at,
                started_at=task.started_at,
                completed_at=task.completed_at,
                depends_on_task_ids=[dependency.depends_on_task_id for dependency in task.dependencies],
            )
            for task in sorted(run.tasks, key=lambda item: item.id)
        ],
        outputs=sorted(
            [output for output in run.outputs],
            key=lambda item: (item.created_at, item.id),
        ),
        artifacts=sorted(
            [artifact for artifact in run.artifacts],
            key=lambda item: (item.created_at, item.id),
        ),
        evidence=sorted(
            [evidence for evidence in run.evidence],
            key=lambda item: (item.created_at, item.id),
        ),
    )


def create_app(settings_overrides: dict | None = None) -> FastAPI:
    settings = build_settings(settings_overrides)
    configure_logging(settings.log_level)
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, session_factory = create_session_factory(settings.database_url)
        init_db(engine)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory

        with session_factory() as session:
            seed_knowledge_assets(session, settings.knowledge_path)

        worker_thread = None
        worker_stop = None
        if settings.embedded_worker:
            worker_thread, worker_stop = start_worker_thread(session_factory, settings)

        yield

        if worker_stop is not None:
            worker_stop.set()
        if worker_thread is not None:
            worker_thread.join(timeout=1)
        engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        description="Production-oriented multi-agent market research and expansion planning platform.",
    )
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request, "settings": settings})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/knowledge", response_model=list[KnowledgeAssetRead], dependencies=[Depends(require_admin_token)])
    def list_knowledge(
        q: str | None = Query(default=None, max_length=120),
        session: Session = Depends(get_session),
    ):
        return search_knowledge_assets(session, q)

    @app.get("/api/runs", response_model=list[RunRead], dependencies=[Depends(require_admin_token)])
    def list_runs(session: Session = Depends(get_session)):
        runs = session.execute(select(Run).order_by(Run.created_at.desc()).limit(20)).scalars().all()
        return [serialize_run(run) for run in runs]

    @app.post("/api/runs", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin_token)])
    def create_run_endpoint(
        payload: RunCreateInput,
        request: Request,
        session: Session = Depends(get_session),
    ):
        run = create_run(session, request.app.state.settings, payload.area, payload.notes, payload.idempotency_key)
        run = session.execute(select(Run).where(Run.id == run.id)).scalar_one()
        return serialize_run(run)

    @app.get("/api/runs/{run_id}", response_model=RunRead, dependencies=[Depends(require_admin_token)])
    def get_run(run_id: str, session: Session = Depends(get_session)):
        run = session.execute(select(Run).where(Run.id == run_id)).scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return serialize_run(run)

    @app.post("/api/runs/{run_id}/process", response_model=RunRead, dependencies=[Depends(require_admin_token)])
    def process_run(run_id: str, request: Request):
        run = process_run_until_complete(request.app.state.session_factory, request.app.state.settings, run_id)
        with request.app.state.session_factory() as fresh_session:
            refreshed = fresh_session.get(Run, run.id)
            return serialize_run(refreshed)

    @app.get("/api/runs/{run_id}/compare", response_model=RunComparisonRead, dependencies=[Depends(require_admin_token)])
    def compare_runs(
        run_id: str,
        other_run_id: str = Query(..., alias="otherRunId"),
        session: Session = Depends(get_session),
    ):
        left = session.get(Run, run_id)
        right = session.get(Run, other_run_id)
        if left is None or right is None:
            raise HTTPException(status_code=404, detail="One or both runs were not found")
        return RunComparisonRead(
            left_run_id=left.id,
            right_run_id=right.id,
            left_status=left.status,
            right_status=right.status,
            left_artifacts=[artifact.title for artifact in left.artifacts],
            right_artifacts=[artifact.title for artifact in right.artifacts],
            left_task_counts=summarize_run_counts(left),
            right_task_counts=summarize_run_counts(right),
        )

    return app


app = create_app()
