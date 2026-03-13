# main.py
import asyncio
import aiohttp
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router
# 把三个交易所都引进来！
from app.exchanges.binance import BinanceAPI
from app.exchanges.okx import OkxAPI
from app.exchanges.gateio import GateioAPI

from app.services.collector import DataCollector
from app.db.timeseries import TimeSeriesDB

background_tasks = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 系统启动，正在初始化【三端全链路】多核采集引擎...")

    # 实例化三大交易所API
    exchanges = [BinanceAPI(), OkxAPI(), GateioAPI()]
    db = TimeSeriesDB()
    session = aiohttp.ClientSession()

    collectors = []

    # 遍历三大交易所，并发获取所有的交易对
    for exchange in exchanges:
        print(f"🔍 正在拉取 {exchange.exchange_name} 所有现货交易对...")
        symbols = await exchange.fetch_symbols(session)
        print(f"✅ {exchange.exchange_name} 成功发现 {len(symbols)} 个现货交易对！")

        # 测试模式：每个交易所切出前 50 个来跑并发！
        test_symbols = symbols[:50]

        # 给每个交易所单独配备一个独立的 DataCollector 引擎！
        # 但它们共用同一个 db (存入同一张表)，共用同一个 websocket_manager (全网广播)
        collector = DataCollector(exchange, test_symbols)
        collectors.append(collector)

        # 启动这个交易所的独立轮询循环和存库循环
        task_loop = asyncio.create_task(collector.run_1m_loop(session))
        task_store = asyncio.create_task(collector.storage_worker(db))

        background_tasks.add(task_loop)
        background_tasks.add(task_store)

    yield

    print("\n🛑 收到退出信号，正在优雅关闭所有服务...")
    for task in background_tasks:
        task.cancel()
    await session.close()
    await db.close()


app = FastAPI(lifespan=lifespan, title="比特鹰 K线系统")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(router)

if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)