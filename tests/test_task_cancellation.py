import asyncio
import unittest

from module.loop_watchdog import cancelTaskSafely


class CancelTaskSafelyTests(unittest.IsolatedAsyncioTestCase):
    async def test_none_and_completed_tasks(self):
        await cancelTaskSafely(None)
        task = asyncio.create_task(asyncio.sleep(0))
        await task
        await cancelTaskSafely(task)

    async def test_child_cancellation_allows_remaining_finalization(self):
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def heartbeat():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        task = asyncio.create_task(heartbeat())
        await started.wait()
        await cancelTaskSafely(task)
        self.assertTrue(cleaned.is_set())
        self.assertTrue(task.cancelled())

    async def test_child_failure_is_consumed(self):
        async def fail():
            raise RuntimeError('heartbeat failed')

        task = asyncio.create_task(fail())
        await asyncio.sleep(0)
        await cancelTaskSafely(task)
        self.assertIsInstance(task.exception(), RuntimeError)

    async def test_already_cancelled_child_is_consumed(self):
        task = asyncio.create_task(asyncio.sleep(100))
        task.cancel()
        await asyncio.sleep(0)
        await cancelTaskSafely(task)
        self.assertTrue(task.cancelled())

    async def test_caller_cancellation_is_not_swallowed(self):
        started = asyncio.Event()
        cleaning = asyncio.Event()
        finished = asyncio.Event()

        async def child():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    finished.set()

        task = asyncio.create_task(child())
        await started.wait()
        caller = asyncio.create_task(cancelTaskSafely(task))
        await cleaning.wait()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(task.done())
        self.assertTrue(finished.is_set())

    async def test_caller_cancel_propagates_even_if_child_swallows_it(self):
        started = asyncio.Event()
        cleaning = asyncio.Event()

        async def child():
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cleaning.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    return

        task = asyncio.create_task(child())
        await started.wait()
        caller = asyncio.create_task(cancelTaskSafely(task))
        await cleaning.wait()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(task.done())
        self.assertFalse(task.cancelled())

    async def test_cleanup_in_cancelled_callers_finally_preserves_cancellation(self):
        started = asyncio.Event()
        finalization = asyncio.Event()
        heartbeat = asyncio.create_task(asyncio.sleep(100))

        async def recorder():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                await cancelTaskSafely(heartbeat)
                finalization.set()

        caller = asyncio.create_task(recorder())
        await started.wait()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(heartbeat.done())
        self.assertTrue(finalization.is_set())

    async def test_rejects_self_cancellation(self):
        with self.assertRaises(ValueError):
            await cancelTaskSafely(asyncio.current_task())


if __name__ == '__main__':
    unittest.main()
