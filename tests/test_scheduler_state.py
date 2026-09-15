from scheduler import InAppScheduler


def test_scheduler_persists_next_run_and_enabled(tmp_path):
    path = str(tmp_path / "jobs.json")
    first = InAppScheduler(path)
    first.add_job("job", {"url": "https://example.com"}, 5, lambda task: None)
    first.jobs["job"].enabled = False
    first._persist()
    second = InAppScheduler(path)
    assert second.load_jobs(lambda task: lambda _: None) == 1
    assert second.jobs["job"].enabled is False
