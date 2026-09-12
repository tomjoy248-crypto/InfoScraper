import threading
import time
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


class InAppScheduler:
    """应用内定时调度器，支持分钟级间隔调度。"""

    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running = False
        self.on_log: Optional[Callable[[str], None]] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def add_job(self, job_id: str, task: Dict, interval_minutes: int, callback: Callable) -> bool:
        if interval_minutes < 1:
            return False
        with self._lock:
            self.jobs[job_id] = Job(job_id, task, interval_minutes, callback)
        self._log(f"添加定时任务 '{job_id}'，每 {interval_minutes} 分钟执行一次")
        return True

    def remove_job(self, job_id: str):
        with self._lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
        self._log(f"删除定时任务 '{job_id}'")

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
                if job.enabled and now >= job.next_run:
                    job.next_run = now + timedelta(minutes=job.interval_minutes)
                    self._log(f"执行定时任务 '{job.job_id}'")
                    try:
                        job.callback(job.task)
                    except Exception as e:
                        self._log(f"定时任务 '{job.job_id}' 执行失败: {e}")
            time.sleep(5)
