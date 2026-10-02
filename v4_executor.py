"""Bounded concurrent execution helpers for authorized asset checks."""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event
from typing import Callable, Iterable, List, Optional, Tuple


@dataclass
class PortResult:
    host: str
    port: int
    state: str
    service: str = ""


COMMON_SERVICES = {80: "http", 443: "https", 8080: "http-alt", 8443: "https-alt", 22: "ssh", 25: "smtp", 53: "dns", 3306: "mysql", 5432: "postgresql"}


def check_port(host: str, port: int, timeout: float = 1.5) -> PortResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return PortResult(host, port, "open", COMMON_SERVICES.get(port, "unknown"))
    except (OSError, TimeoutError):
        return PortResult(host, port, "closed")


def run_checks(items: Iterable[Tuple[str, int]], workers: int = 8,
               cancelled: Optional[Event] = None,
               on_progress: Optional[Callable[[int, int, PortResult], None]] = None) -> List[PortResult]:
    jobs = list(items)
    total = len(jobs)
    done = 0
    results: List[PortResult] = []
    cancelled = cancelled or Event()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 32))) as pool:
        futures = [pool.submit(check_port, host, port) for host, port in jobs]
        for future in as_completed(futures):
            if cancelled.is_set():
                break
            result = future.result()
            results.append(result)
            done += 1
            if on_progress:
                on_progress(done, total, result)
    return results
