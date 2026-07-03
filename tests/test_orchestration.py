from __future__ import annotations

from sqlalchemy import select

from app.models import Run, Task
from app.orchestration import TASK_BLUEPRINTS, create_run, process_next_task


def test_create_run_builds_expected_task_graph(client):
    app = client.app
    with app.state.session_factory() as session:
        run = create_run(session, app.state.settings, "Baltimore, Maryland", notes="Test")
        tasks = session.execute(select(Task).where(Task.run_id == run.id).order_by(Task.id)).scalars().all()

    assert [task.kind for task in tasks] == [blueprint.kind for blueprint in TASK_BLUEPRINTS]
    assert tasks[0].status == "queued"
    assert all(task.status == "blocked" for task in tasks[4:])


def test_task_statuses_progress_to_completion(client):
    app = client.app
    with app.state.session_factory() as session:
        run = create_run(session, app.state.settings, "Columbia, Maryland")
        run_id = run.id

    steps = 0
    while process_next_task(app.state.session_factory, app.state.settings):
        steps += 1
        if steps > 20:
            break

    with app.state.session_factory() as session:
        refreshed = session.execute(select(Run).where(Run.id == run_id)).scalar_one()
        assert refreshed.status == "completed"
        assert all(task.status == "done" for task in refreshed.tasks)
