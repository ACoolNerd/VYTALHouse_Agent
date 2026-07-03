from __future__ import annotations

import logging
import threading
import time

from app.config import build_settings
from app.database import create_session_factory, init_db
from app.knowledge import seed_knowledge_assets
from app.orchestration import process_next_task


LOGGER = logging.getLogger(__name__)


class WorkerService:
    def __init__(self, session_factory, settings, stop_event: threading.Event | None = None):
        self.session_factory = session_factory
        self.settings = settings
        self.stop_event = stop_event or threading.Event()

    def run_forever(self) -> None:
        LOGGER.info("worker_started")
        while not self.stop_event.is_set():
            processed = process_next_task(self.session_factory, self.settings)
            if not processed:
                time.sleep(self.settings.worker_poll_seconds)


def start_worker_thread(session_factory, settings):
    stop_event = threading.Event()
    service = WorkerService(session_factory, settings, stop_event=stop_event)
    thread = threading.Thread(target=service.run_forever, daemon=True, name="vytal-worker")
    thread.start()
    return thread, stop_event


def main() -> None:
    settings = build_settings()
    engine, session_factory = create_session_factory(settings.database_url)
    init_db(engine)
    with session_factory() as session:
        seed_knowledge_assets(session, settings.knowledge_path)
    WorkerService(session_factory, settings).run_forever()


if __name__ == "__main__":
    main()
