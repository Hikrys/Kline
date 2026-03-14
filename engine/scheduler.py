# app/services/scheduler.py
import asyncio
import aiohttp
from typing import List
from exchanges.base import BaseExchange
from storage.timeseries import TimeSeriesDB
from server.ws_handler import manager


class DataCollector:
    def __init__(self, exchange_api: BaseExchange, symbols: List[str]):
        self.api = exchange_api
        self.symbols = symbols

        # 这个 Queue 相当于 Go 里的带缓冲的 Channel: chan StandardKline
        # 后面我们要写的“入库服务”和“WebSocket推送”都会从这个 Channel 里拿数据！
        self.queue = asyncio.Queue(maxsize=5000)

    async def fetch_worker(self, session: aiohttp.ClientSession, symbol: str, interval: str):
        # 指数退避重试
        max_retries = 3
        for attempt in range(max_retries):
            try:
                kline = await self.api.fetch_kline(session, symbol, interval)
                if kline:
                    # 获取成功，塞进 Channel！
                    await self.queue.put(kline)
                    print(f"[{self.api.exchange_name}] 采集成功: {symbol}")
                    return
            except Exception as e:
                print(f"[{self.api.exchange_name}] 采集 {symbol} 失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            # 指数退避机制。第一次失败等 1秒(2^0)，第二次等 2秒(2^1)，第三次等 4秒(2^2)
            await asyncio.sleep(2 ** attempt)

    async def run_1m_loop(self, session: aiohttp.ClientSession):
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

            # 均匀分布，避免瞬间突发
            # 60 秒 / 交易对数量 = 每次发请求的间隔时间
            # 如果有 1200 个对，每次间隔就是 0.05 秒。极其平滑，不会触发 Rate Limit！
            delay_between_requests = 60.0 / total_symbols

            # 采用 asyncio.TaskGroup (相当于 Go 里的 errgroup.Group)
            # 当 with 块结束时，它会自动等待里面所有的 Task 执行完毕！
            try:
                async with asyncio.TaskGroup() as tg:
                    for symbol in self.symbols:
                        # 开一个 Goroutine 去抓取
                        tg.create_task(self.fetch_worker(session, symbol, "1m"))

                        # 休眠，达到匀速下发！
                        await asyncio.sleep(delay_between_requests)
            except* Exception as e:
                # Python 3.11+ 的新语法 except*，专门用来捕获 TaskGroup 里的并发异常
                print(f"本轮采集出现异常: {e}")

            # 计算本轮总耗时
            elapsed = asyncio.get_event_loop().time() - start_time
            # 算出距离下一分钟的 00 秒还差多少时间，睡够这个时间，做到完美按分钟对齐！
            sleep_time = max(0, 60.0 - elapsed)
            print(f"🏁 本轮任务下发完毕！耗时 {elapsed:.2f} 秒，等待 {sleep_time:.2f} 秒后开启下一轮...")

            await asyncio.sleep(sleep_time)

    async def storage_worker(self, db: TimeSeriesDB):
        batch_size = 50
        batch = []

        while True:
            try:
                kline = await self.queue.get()
                batch.append(kline)

                # 从队列拿到K线，存库，除了存库，立刻广播给所有订阅者
                await manager.broadcast_kline(kline)

                if len(batch) >= batch_size:
                    to_insert = batch[:]
                    batch.clear()
                    await db.write_batch(to_insert)

                self.queue.task_done()
            except asyncio.CancelledError:
                if batch:
                    await db.write_batch(batch)
                break
            except Exception as e:
                print(f" 存储消费者异常: {e}")