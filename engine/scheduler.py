# app/services/scheduler.py
import asyncio
import aiohttp
import orjson
import redis.asyncio as aioredis
from core.state import state
from config import settings
from typing import List
from exchanges.base import BaseExchange
from storage.timeseries import TimeSeriesDB
from server.ws_handler import manager
from engine.rate_limiter import RateLimiter
from engine.queue import TaskQueue



class DataCollector:
    def __init__(self, exchange_api: BaseExchange, symbols: List[str]):
        self.api = exchange_api
        self.symbols = symbols

        self.queue = TaskQueue()
        # 初始化Redis发布端客户端
        self.redis_client = aioredis.from_url(settings.redis.url)

    async def fetch_worker(self, session: aiohttp.ClientSession, symbol: str, interval: str) -> None:
        # 指数退避重试
        max_retries = 3
        for attempt in range(max_retries):
            try:
                kline = await self.api.fetch_kline(session, symbol, interval)
                if kline:
                    await self.queue.put(kline)
                    print(f"[{self.api.exchange_name}] 采集成功: {symbol}")
                    return
            except Exception as e:
                print(f"[{self.api.exchange_name}] 采集 {symbol} 失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            # 指数退避机制。第一次失败等 1秒(2^0)，第二次等 2秒(2^1)，第三次等 4秒(2^2)
            await asyncio.sleep(2 ** attempt)

    async def run_1m_loop(self, session: aiohttp.ClientSession) -> None:
        """
        每分钟执行一次的轮询主循环 (全场最核心逻辑)
        """
        while True:
            # 记录这一轮开始的时间
            start_time = asyncio.get_event_loop().time()
            total_symbols = len(self.symbols)

            if total_symbols == 0:
                print("没有交易对，等待下一分钟...")
                await asyncio.sleep(60)
                continue

            print(f"开始本轮采集，共 {total_symbols} 个交易对...")

            limiter = RateLimiter(total_symbols, window_seconds=60.0)
            try:
                async with asyncio.TaskGroup() as tg:
                    for symbol in self.symbols:
                        # 开一个 Goroutine 去抓取
                        tg.create_task(self.fetch_worker(session, symbol, "1m"))
                        await limiter.wait()
            except* Exception as e:
                # Python 3.11+ 的新语法 except*，专门用来捕获 TaskGroup 里的并发异常
                print(f"本轮采集出现异常: {e}")

            # 计算本轮总耗时
            elapsed = asyncio.get_event_loop().time() - start_time
            # 算出距离下一分钟的 00 秒还差多少时间，睡够这个时间，做到完美按分钟对齐！
            sleep_time = max(0, 60.0 - elapsed)
            print(f"🏁 本轮任务下发完毕！耗时 {elapsed:.2f} 秒，等待 {sleep_time:.2f} 秒后开启下一轮...")

            await asyncio.sleep(sleep_time)

    async def storage_worker(self, db: TimeSeriesDB) -> None:
        batch_size = 50
        batch = []

        while True:
            try:
                # 每次循环，更新全局状态里的队列深度，供前端 API 查询
                state.queue_depth = self.queue.qsize()
                kline = await self.queue.get()
                batch.append(kline)

                # 把数据打进 Redis 广播中
                payload = {
                    "type": "realtime",
                    "data": kline.model_dump()
                }
                await self.redis_client.publish("kline:broadcast", orjson.dumps(payload))

                if len(batch) >= batch_size:
                    to_insert = batch[:]
                    batch.clear()
                    await db.write_batch(to_insert)

                self.queue.task_done()
            except asyncio.CancelledError:
                if batch:
                    print("检测到退出信号，正在将内存数据写入 WAL 日志...")
                    import os
                    from storage.wal import WALManager
                    emergency_wal = WALManager(os.path.join(os.getcwd(), "wal.log"))
                    # 使用当前事件循环紧急跑完这段协程
                    asyncio.get_event_loop().run_until_complete(emergency_wal.append(batch))
                break
            except Exception as e:
                print(f"存储消费者异常: {e}")