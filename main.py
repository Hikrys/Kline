import sys
import asyncio
import aiohttp
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles


# 引入配置文件
from config import settings
from core.state import state

from server.routes import router
from exchanges.binance import BinanceAPI
from exchanges.okx import OkxAPI
from exchanges.gateio import GateioAPI
from engine.scheduler import DataCollector
from storage.timeseries import TimeSeriesDB
from server.ws_handler import manager

background_tasks = set()


async def hourly_symbol_refresh(exchanges: list, session: aiohttp.ClientSession):
    """
    每小时定时刷新一次全量交易对，纳入新上线的币种
    """
    while True:
        # 挂起 1 小时 (3600 秒)
        await asyncio.sleep(3600)
        print("[定时任务] 触发每小时刷新全网交易对列表...")
        for exchange in exchanges:
            try:
                symbols = await exchange.fetch_symbols(session)
                if symbols:
                    state.symbols[exchange.exchange_name] = symbols
                    print(f" [定时任务] {exchange.exchange_name} 交易对已更新，共 {len(symbols)} 个")
            except Exception as e:
                print(f" [定时任务] {exchange.exchange_name} 更新失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(" 系统启动，读取 config.yaml 配置...")

    exchanges = [BinanceAPI(), OkxAPI(), GateioAPI()]
    db = TimeSeriesDB()

    # 针对可能存在的代理网络，关闭 SSL 严格验证以防断连
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    # 启动时立刻获取一次全量交易对
    for exchange in exchanges:
        print(f" 正在拉取 {exchange.exchange_name} 所有现货交易对...")
        symbols = await exchange.fetch_symbols(session)

        # 存入全局内存状态 (供 REST API 和 前端下拉框使用)
        state.symbols[exchange.exchange_name] = symbols
        print(f" {exchange.exchange_name} 成功发现 {len(symbols)} 个现货交易对！")

        #每个交易所切 50 个来跑并发采集
        test_symbols = symbols[:50]

        # 拉起采集引擎和数据库写入消费者
        collector = DataCollector(exchange, test_symbols)
        task_loop = asyncio.create_task(collector.run_1m_loop(session))
        task_store = asyncio.create_task(collector.storage_worker(db))

        background_tasks.add(task_loop)
        background_tasks.add(task_store)

    #  拉起 每小时自动刷新 的后台监控任务
    refresh_task = asyncio.create_task(hourly_symbol_refresh(exchanges, session))
    background_tasks.add(refresh_task)

    # 启动 Redis 全局监听任务
    redis_task = asyncio.create_task(manager.listen_to_redis())
    background_tasks.add(redis_task)

    yield

    print("\n收到退出信号，正在关闭所有服务...")

    # 先给所有后台任务发送取消信号
    for task in background_tasks:
        task.cancel()

    # 等待所有任务真正完成收尾工作
    # 给 storage_worker 留出足够的时间，把内存里的残余数据平滑地写进 wal.log！
    print("等待后台队列排空与日志落盘...")
    await asyncio.gather(*background_tasks, return_exceptions=True)

    # 任务全都安全停止后，最后再关闭底层的 HTTP 连接和数据库连接！
    print("正在断开数据库与网络连接...")
    await session.close()
    await db.close()
    print("系统安全退出。")


app = FastAPI(lifespan=lifespan, title="比特鹰 K线系统")
app.mount("/web", StaticFiles(directory="web"), name="web")
app.include_router(router)

if __name__ == "__main__":
    if sys.platform != "win32":
        try:
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            print("Linux 环境检测到，换用 uvloop 极致性能事件循环")
        except ImportError:
            pass
    else:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 从 settings 读取绑定的 IP 和端口
    uvicorn.run("main:app", host=settings.server.host, port=settings.server.port, reload=False)