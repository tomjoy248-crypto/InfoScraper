import threading
import time
import json
import os
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional


class Job:
    def __init__(self, job_id: str, task: Dict, interval_minutes: int, callback: Callable):
        self.job_id = job_id
        self.task = task
        self.interval_minutes = interval_minutes
        self.callback = callback
        self.next_run = datetime.now() + timedelta(minutes=interval_minutes)
        self.enabled = True
        self.running = False


class InAppScheduler:
    """应用内定时调度器，支持分钟级间隔调度。"""

    def __init__(self, storage_path: Optional[str] = None):
        self.jobs: Dict[str, Job] = {}
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running = False
        self._stop_event = threading.Event()
        self.on_log: Optional[Callable[[str], None]] = None
        self.storage_path = storage_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler_jobs.json")

    def _persist(self):
        """Persist schedules without serializing callback objects."""
        payload = [{"id": j.job_id, "task": j.task, "interval": j.interval_minutes,
                    "next_run": j.next_run.isoformat(), "enabled": j.enabled}
                   for j in self.jobs.values()]
        temp = self.storage_path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp, self.storage_path)

    def load_jobs(self, callback_factory: Callable[[Dict], Callable]) -> int:
        """Load persisted jobs and create callbacks through ``callback_factory``."""
        if not os.path.exists(self.storage_path):
            return 0
        try:
            with open(self.storage_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for item in payload:
                if int(item.get("interval", 0)) < 1:
                    continue
                try:
                    callback = callback_factory(item["id"], item["task"])
                except TypeError:
                    callback = callback_factory(item["task"])
                self.add_job(item["id"], item["task"], int(item["interval"]), callback)
                job = self.jobs[item["id"]]
                if item.get("next_run"):
                    try: job.next_run = datetime.fromisoformat(item["next_run"])
                    except ValueError: pass
                job.enabled = bool(item.get("enabled", True))
            return len(self.jobs)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._log(f"定时任务加载失败: {exc}")
            return 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    def add_job(self, job_id: str, task: Dict, interval_minutes: int, callback: Callable) -> bool:
        if interval_minutes < 1:
            return False
        with self._lock:
            self.jobs[job_id] = Job(job_id, task, interval_minutes, callback)
            self._persist()
        self._log(f"添加定时任务 '{job_id}'，每 {interval_minutes} 分钟执行一次")
        return True

    def remove_job(self, job_id: str):
        with self._lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                self._persist()
        self._log(f"删除定时任务 '{job_id}'")

    def finish(self, job_id: str):
        with self._lock:
            job = self.jobs.get(job_id)
            if job:
                job.running = False

    def list_jobs(self) -> List[Dict]:
        with self._lock:
            return [
                {
                    "id": j.job_id,
                    "interval": j.interval_minutes,
                    "next_run": j.next_run.isoformat(),
                    "enabled": j.enabled,
                }
                for j in self.jobs.values()
            ]

    def _log(self, msg: str):
        if self.on_log:
            self.on_log(msg)

    def _loop(self):
        while self._running:
            now = datetime.now()
            with self._lock:
                jobs_snapshot = list(self.jobs.values())
            for job in jobs_snapshot:
                if job.enabled and not job.running and now >= job.next_run:
                    job.running = True
                    job.next_run = now + timedelta(minutes=job.interval_minutes)
                    with self._lock:
                        self._persist()
                    self._log(f"执行定时任务 '{job.job_id}'")
                    try:
                        job.callback(job.task)
                    except Exception as e:
                        self._log(f"定时任务 '{job.job_id}' 执行失败: {e}")
                        job.running = False
            self._stop_event.wait(5)
