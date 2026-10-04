"""Shared cancellation primitive for scraper, HTTP, and browser tasks."""

import threading


class CancellationToken:
    """Thread-safe cancellation token with interruptible waiting."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation to all cooperating operations."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Return whether cancellation was requested."""
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        """Wait up to timeout seconds, returning True if cancelled."""
        return self._event.wait(timeout)
