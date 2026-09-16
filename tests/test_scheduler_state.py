from scheduler import InAppScheduler
import time
import threading
from datetime import datetime


def test_scheduler_persists_next_run_and_enabled(tmp_path):
    path = str(tmp_path / "jobs.json")
    first = InAppScheduler(path)
    first.add_job("job", {"url": "https://example.com"}, 5, lambda task: None)
    first.jobs["job"].enabled = False
    first._persist()
    second = InAppScheduler(path)
    assert second.load_jobs(lambda _job_id, task: lambda _: None) == 1
    assert second.jobs["job"].enabled is False

def test_scheduler_running_flag_blocks_overlap(tmp_path):
    scheduler = InAppScheduler(str(tmp_path / "jobs.json"))
    calls = []
    scheduler.add_job("job", {}, 1, lambda _: calls.append(1))
    job = scheduler.jobs["job"]
    job.running = True
    job.next_run = scheduler.jobs["job"].next_run.replace(year=2000)
    scheduler._running = True
    scheduler._running = False
    assert calls == []

def test_scheduler_long_callback_does_not_overlap(tmp_path):
    scheduler = InAppScheduler(str(tmp_path / "long.json"))
    calls = []
    def callback(_):
        calls.append("start")
        time.sleep(0.15)
        calls.append("end")
    scheduler.add_job("job", {}, 1, callback)
    job = scheduler.jobs["job"]
    job.next_run = job.next_run.replace(year=2000)
    scheduler._running = True
    thread = __import__("threading").Thread(target=scheduler._loop, daemon=True)
    thread.start(); time.sleep(0.25); scheduler.stop(); thread.join(timeout=1)
    assert calls.count("start") == 1


def test_restored_async_job_finishes_and_can_run_again(tmp_path):
    path = str(tmp_path / "restore.json")
    original = InAppScheduler(path)
    original.add_job("job", {"task_name": "restored"}, 1, lambda _: None)
    restored = InAppScheduler(path)
    calls = []

    def factory(job_id, _task):
        def callback(task):
            def worker():
                calls.append((threading.current_thread().name, task["task_name"]))
                restored.finish(job_id)
            threading.Thread(target=worker, daemon=True).start()
        return callback

    assert restored.load_jobs(factory) == 1
    restored.jobs["job"].next_run = datetime(2000, 1, 1)
    restored.start()
    deadline = time.monotonic() + 1
    while (not calls or restored.jobs["job"].running) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(calls) == 1
    assert restored.jobs["job"].running is False
    restored.jobs["job"].next_run = datetime(2000, 1, 1)
    restored._stop_event.set()
    deadline = time.monotonic() + 1
    while len(calls) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    restored.stop()
    assert len(calls) == 2
    assert all(name != threading.current_thread().name for name, _ in calls)
