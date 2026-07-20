# -*- coding: utf-8 -*-
"""Short cross-process locks for filesystem Runtime stores.

Lock files are stable coordination inodes and are intentionally never unlinked
after release.  Removing an advisory lock file can create two lock domains when
one process still has the old inode open.
"""

from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
import time
from types import TracebackType

from .errors import LockTimeoutError, RuntimeFileValidationError


class CrossProcessFileLock:
    """An exclusive, process-crash-safe ``fcntl.flock`` lock.

    The lock only protects writers that share this primitive.  Runtime locks
    must therefore be acquired at a single documented boundary and kept out of
    model/provider calls.  The operating system releases the lock when the
    descriptor or process exits; the file itself contains no authoritative
    state.

    Pass ``shared=True`` for a ``LOCK_SH`` reader lock.  Reader locks do not
    block each other, so concurrent read-only polling never serializes against
    itself; they still exclude ``LOCK_EX`` writers (and vice versa).  POSIX
    ``flock`` merges multiple descriptors on the same inode within one process,
    so reader locks are safe across threads of the same process.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        timeout_seconds: float | None = 10.0,
        poll_interval_seconds: float = 0.01,
        mode: int = 0o600,
        shared: bool = False,
    ) -> None:
        self.path = Path(path)
        if timeout_seconds is not None and timeout_seconds < 0:
            raise RuntimeFileValidationError(
                "lock timeout must be non-negative or None",
            )
        if poll_interval_seconds <= 0:
            raise RuntimeFileValidationError(
                "lock poll interval must be positive",
            )
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.mode = mode
        self.shared = shared
        self._descriptor: int | None = None

    @property
    def acquired(self) -> bool:
        return self._descriptor is not None

    def acquire(self) -> CrossProcessFileLock:
        if self._descriptor is not None:
            raise RuntimeFileValidationError(
                f"lock is not re-entrant: {self.path}",
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, self.mode)
        os.fchmod(descriptor, self.mode)
        lock_op = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
        lock_op |= fcntl.LOCK_NB
        started = time.monotonic()
        try:
            while True:
                try:
                    fcntl.flock(descriptor, lock_op)
                    self._descriptor = descriptor
                    return self
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise
                if self.timeout_seconds is not None:
                    elapsed = time.monotonic() - started
                    if elapsed >= self.timeout_seconds:
                        raise LockTimeoutError(self.path, self.timeout_seconds)
                    remaining = self.timeout_seconds - elapsed
                    time.sleep(min(self.poll_interval_seconds, remaining))
                else:
                    time.sleep(self.poll_interval_seconds)
        except BaseException:
            os.close(descriptor)
            raise

    def release(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            return
        self._descriptor = None
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def __enter__(self) -> CrossProcessFileLock:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.release()
