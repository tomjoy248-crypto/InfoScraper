import json
import threading
import time
from datetime import datetime

from scheduler import InAppScheduler


def _wait_until(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_restored_job_runs_in_worker_finishes_and_repeats(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([{
        "id": "restored", "task": {"name": "saved"}, "interval": 1,
        "next_run": "2000-01-01T00:00:00", "enabled": True,
    }]), encoding="utf-8")
    scheduler = InAppScheduler(str(path))
    calls = []
    worker_threads = []

    def callback_factory(job_id, _task):
        def callback(task):
            def run():
                try:
                    calls.append(task["name"])
                    worker_threads.append(threading.current_thread().name)
                finally:
                    scheduler.finish(job_id)
            threading.Thread(target=run, daemon=True, name="restored-worker").start()
        return callback

    assert scheduler.load_jobs(callback_factory) == 1
    scheduler.start()
    assert _wait_until(lambda: len(calls) == 1 and not scheduler.jobs["restored"].running)

    scheduler.jobs["restored"].next_run = datetime(2000, 1, 1)
    scheduler._stop_event.set()
    assert _wait_until(lambda: len(calls) == 2 and not scheduler.jobs["restored"].running)
    scheduler.stop()

    assert calls == ["saved", "saved"]
    assert worker_threads == ["restored-worker", "restored-worker"]
