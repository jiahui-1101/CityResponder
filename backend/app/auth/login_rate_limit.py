"""Small process-local throttling for failed account login attempts."""

from __future__ import annotations

from collections import OrderedDict, deque
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable


class LoginRateLimiter:
    """Temporarily throttle repeated failures for one normalized account.

    This intentionally avoids IP-wide lockouts, which are unsafe behind a
    shared proxy or Cloudflare Tunnel. State is bounded and expires quickly;
    this limiter does not disable or persistently lock user accounts.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        window_seconds: float = 60.0,
        max_accounts: int = 10_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_attempts < 1 or window_seconds <= 0 or max_accounts < 1:
            raise ValueError("login throttle limits must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_accounts = max_accounts
        self._clock = clock
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    @staticmethod
    def _key(email: str) -> str:
        normalized = email.strip().casefold()
        return sha256(normalized.encode("utf-8")).hexdigest()

    def _prune_account(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        timestamps = self._failures.get(key)
        if timestamps is None:
            return
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if not timestamps:
            self._failures.pop(key, None)

    def retry_after(self, email: str) -> int | None:
        now = self._clock()
        key = self._key(email)
        with self._lock:
            self._prune_account(key, now)
            timestamps = self._failures.get(key)
            if timestamps is None or len(timestamps) < self.max_attempts:
                return None
            self._failures.move_to_end(key)
            return max(1, ceil(timestamps[0] + self.window_seconds - now))

    def record_failure(self, email: str) -> None:
        now = self._clock()
        key = self._key(email)
        with self._lock:
            self._prune_account(key, now)
            timestamps = self._failures.get(key)
            if timestamps is None:
                while len(self._failures) >= self.max_accounts:
                    self._failures.popitem(last=False)
                timestamps = deque()
                self._failures[key] = timestamps
            else:
                self._failures.move_to_end(key)
            timestamps.append(now)

    def reset(self, email: str) -> None:
        key = self._key(email)
        with self._lock:
            self._failures.pop(key, None)


login_rate_limiter = LoginRateLimiter()
