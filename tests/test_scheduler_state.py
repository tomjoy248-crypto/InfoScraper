from scheduler import InAppScheduler
import time


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
