"""One resident PEFT model, serialized across loading, inference and eviction."""

from __future__ import annotations

import gc
import logging
import sys
import threading
import time
import traceback
from collections.abc import Callable
from typing import TypeVar

from smartevent_ai.domain.errors import ModelUnavailable

T = TypeVar("T")
logger = logging.getLogger(__name__)


class SequentialPeftPool:
    """Drop old weights completely; never keep a second CPU copy for swapping."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._unloaders: dict[str, Callable[[], None]] = {}
        self._active: str | None = None
        self._closed = False
        self._switches = 0
        self._operations = 0
        self._last_seconds = 0.0

    def register(self, name: str, unload: Callable[[], None]) -> None:
        with self._lock:
            if self._closed or name in self._unloaders:
                raise ValueError("Duplicate model or closed sequential pool")
            self._unloaders[name] = unload

    @staticmethod
    def _release_memory() -> None:
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def run(self, name: str, operation: Callable[[], T]) -> T:
        # This lock covers the whole callback, including tokenizer inputs and outputs.
        # A timed-out HTTP coroutine cannot cancel its worker thread, so later
        # requests must still wait here until that worker really finishes.
        with self._lock:
            if self._closed or name not in self._unloaders:
                raise ModelUnavailable("Sequential model runtime unavailable")
            started = time.monotonic()
            if self._active != name:
                previous = self._active
                if previous is not None:
                    self._unloaders[previous]()
                    self._release_memory()
                with self._status_lock:
                    self._active = name
                    self._switches += int(previous is not None)
                logger.info("Sequential PEFT activation: %s -> %s", previous, name)
            try:
                return operation()
            except BaseException as exc:
                # Failed loading may retain tensors in completed traceback frames.
                traceback.clear_frames(exc.__traceback__)
                self._unloaders[name]()
                with self._status_lock:
                    self._active = None
                self._release_memory()
                raise
            finally:
                with self._status_lock:
                    self._operations += 1
                    self._last_seconds = round(time.monotonic() - started, 3)
                logger.info(
                    "Sequential PEFT operation: %s completed in %.3fs", name, self._last_seconds
                )

    def status(self) -> dict[str, object]:
        # Health reads do not wait behind model generation.
        with self._status_lock:
            return {
                "mode": "sequential",
                "active_model": self._active,
                "switches": self._switches,
                "operations": self._operations,
                "last_operation_seconds": self._last_seconds,
            }

    def close(self) -> None:
        with self._lock:
            for unload in self._unloaders.values():
                unload()
            with self._status_lock:
                self._active = None
                self._closed = True
            self._release_memory()
