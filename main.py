# main.py
import asyncio
import aiohttp
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.endpoints import router
from app.exchanges.binance import BinanceAPI
from app.services.collector import DataCollector
from app.db.timeseries import TimeSeriesDB

# 全局变量，用来在后台运行我们的任务
background_tasks = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 的生命周期管理器。
    相当于 Go 里的 main 函数刚启动时执行的逻辑，以及 defer 执行的清理逻辑。
    """
    print("🚀 系统启动，正在初始化后台采集引擎...")
    binance = BinanceAPI()
    db = TimeSeriesDB()

    # 建立一个全局的长连接给爬虫用
    session = aiohttp.ClientSession()

    symbols = await binance.fetch_symbols(session)
    # 测试模式：抽取 10 个跑跑看。如果想全量跑，就把 [:10] 删掉！
    test_symbols = symbols[:10]

    collector = DataCollector(binance, test_symbols)

    # 把采集任务和存储任务放到后台运行 (相当于 go run_1m_loop())
    task1 = asyncio.create_task(collector.run_1m_loop(session))
    task2 = asyncio.create_task(collector.storage_worker(db))
    background_tasks.add(task1)
    background_tasks.add(task2)

    yield  # 这里是分水岭！上面的代码在启动时运行，下面的代码在关闭时运行

    print("\n🛑 收到退出信号，正在关闭系统...")
    for task in background_tasks:
        task.cancel()
    await session.close()
    await db.close()


# 实例化 FastAPI 框架
app = FastAPI(lifespan=lifespan, title="比特鹰 K线系统")

# 挂载我们刚才写的路由
app.include_router(router)

if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 启动 Uvicorn Web 服务器，监听 8000 端口
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)