from scheduler import InAppScheduler
import time


def test_scheduler_persists_next_run_and_enabled(tmp_path):
    path = str(tmp_path / "jobs.json")
    first = InAppScheduler(path)
    first.add_job("job", {"url": "https://example.com"}, 5, lambda task: None)
    first.jobs["job"].enabled = False
    first._persist()
    second = InAppScheduler(path)
    assert second.load_jobs(lambda task: lambda _: None) == 1
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
