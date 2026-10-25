"""Bounded private thread workers; capacity belongs to actual concurrent futures."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor


class WorkBusy(RuntimeError):
    pass


class BoundedWorkers:
    def __init__(self, workers, capacity, name):
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self._capacity = capacity
        self._pending = set()
        self._lock = threading.Lock()
        self._closed = False

    async def run(self, fn, *args):
        with self._lock:
            if self._closed or len(self._pending) >= self._capacity:
                raise WorkBusy('worker closed or full')
            future = self._executor.submit(fn, *args)
            self._pending.add(future)
        # Register outside the lock: a finished Future invokes callbacks inline.
        future.add_done_callback(self._finished)
        # Cancellation of the requesting coroutine MUST NOT free worker capacity.
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(self._consume_exception)
        return await asyncio.shield(wrapped)

    def _finished(self, future):
        with self._lock:
            self._pending.discard(future)

    @staticmethod
    def _consume_exception(future):
        if not future.cancelled():
            future.exception()

    def close(self):
        with self._lock:
            self._closed = True

    async def shutdown(self):
        self.close()
        # Finish admitted writes; never abandon a committed action halfway through.
        await asyncio.to_thread(self._executor.shutdown, wait=True)
