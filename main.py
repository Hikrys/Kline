# main.py
import sys
import asyncio
import aiohttp
import uvicorn
from contextlib import asynccontextmanager

from config import settings
from core.state import state
from exchanges.binance import BinanceAPI
from exchanges.okx import OkxAPI
from exchanges.gateio import GateioAPI
from engine.scheduler import DataCollector
from storage.timeseries import TimeSeriesDB
from server.ws_handler import manager
from server.app import create_app

background_tasks = set()


async def hourly_symbol_refresh(exchanges: list, session: aiohttp.ClientSession) -> None:
    while True:
        await asyncio.sleep(3600)
        print("[定时任务] 触发每小时刷新全网交易对列表...")
        for exchange in exchanges:
            try:
                symbols = await exchange.fetch_symbols(session)
                if symbols:
                    state.symbols[exchange.exchange_name] = symbols
            except Exception as e:
                pass


@asynccontextmanager
async def lifespan(app):
    print("系统启动，读取 config.yaml 配置...")
    exchanges = [BinanceAPI(), OkxAPI(), GateioAPI()]
    db = TimeSeriesDB()
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    for exchange in exchanges:
        print(f"正在拉取 {exchange.exchange_name} 所有现货交易对...")
        symbols = await exchange.fetch_symbols(session)
        state.symbols[exchange.exchange_name] = symbols
        print(f"{exchange.exchange_name} 成功发现 {len(symbols)} 个现货交易对！")

        test_symbols = symbols[:50]

        collector = DataCollector(exchange, test_symbols)
        task_loop = asyncio.create_task(collector.run_1m_loop(session))
        task_store = asyncio.create_task(collector.storage_worker(db))
        background_tasks.add(task_loop)
        background_tasks.add(task_store)

    refresh_task = asyncio.create_task(hourly_symbol_refresh(exchanges, session))
    redis_task = asyncio.create_task(manager.listen_to_redis())
    background_tasks.add(refresh_task)
    background_tasks.add(redis_task)

    yield

    print("\n收到退出信号，正在优雅关闭所有服务...")
    for task in background_tasks:
        task.cancel()
    print("等待后台队列排空与日志落盘...")
    await asyncio.gather(*background_tasks, return_exceptions=True)
    await session.close()
    await db.close()
    print("系统安全退出。")


app = create_app(lifespan)

if __name__ == "__main__":
    if sys.platform != "win32":
        try:
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            print("Linux 环境检测到，已启用 uvloop！")
        except ImportError:
            pass
    else:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run("main:app", host=settings.server.host, port=settings.server.port, reload=False)