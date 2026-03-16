# engine/queue.py
import asyncio
from models.kline import StandardKline


class TaskQueue:
    """
    独立封装的异步消息队列
    """
    def __init__(self, maxsize: int = 5000) -> None:
        self._queue: asyncio.Queue[StandardKline] = asyncio.Queue(maxsize=maxsize)

    async def put(self, item: StandardKline) -> None:
        await self._queue.put(item)

    async def get(self) -> StandardKline:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()