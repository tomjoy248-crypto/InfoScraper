import json

from scheduler import InAppScheduler


def factory(_job_id, _task):
    return lambda _task: None


def test_load_jobs_returns_zero_without_file(tmp_path):
    scheduler = InAppScheduler(str(tmp_path / "missing.json"))
    assert scheduler.load_jobs(factory) == 0


def test_load_jobs_restores_metadata(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([{
        "id": "job", "task": {"name": "saved"}, "interval": 7,
        "next_run": "2030-01-02T03:04:05", "enabled": False,
    }]), encoding="utf-8")
    scheduler = InAppScheduler(str(path))
    assert scheduler.load_jobs(factory) == 1
    job = scheduler.jobs["job"]
    assert job.interval_minutes == 7
    assert job.enabled is False
    assert job.next_run.isoformat() == "2030-01-02T03:04:05"


def test_load_jobs_skips_invalid_interval(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([{"id": "bad", "task": {}, "interval": 0}]), encoding="utf-8")
    scheduler = InAppScheduler(str(path))
    assert scheduler.load_jobs(factory) == 0
    assert scheduler.jobs == {}


def test_load_jobs_returns_zero_for_corrupt_file(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("{not-json", encoding="utf-8")
    scheduler = InAppScheduler(str(path))
    assert scheduler.load_jobs(factory) == 0

