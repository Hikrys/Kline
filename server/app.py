# server/app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server.routes import router


def create_app(lifespan_handler) -> FastAPI:
    """
    工厂函数：创建并配置 FastAPI 应用实例
    """
    app = FastAPI(lifespan=lifespan_handler, title="比特鹰 K线系统")

    # 挂载前端静态文件 (对应 web 目录)
    app.mount("/static", StaticFiles(directory="web"), name="static")

    # 注册路由
    app.include_router(router)

    return app