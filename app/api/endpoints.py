# app/api/endpoints.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from app.services.websocket_manager import manager
import orjson
import os
# 防呆设计
import json
import aiohttp
from fastapi.responses import JSONResponse


router = APIRouter()


@router.get("/")
async def get_index():
    """
    当浏览器访问根目录时，直接返回我们写好的静态 HTML 页面
    """
    html_path = os.path.join(os.getcwd(), "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)

            action = data.get("action")
            symbol = data.get("symbol")

            if action == "subscribe" and symbol:
                await manager.subscribe(websocket, symbol)
                await websocket.send_text(orjson.dumps({"status": "subscribed", "symbol": symbol}).decode('utf-8'))

            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe(websocket, symbol)
                await websocket.send_text(orjson.dumps({"status": "unsubscribed", "symbol": symbol}).decode('utf-8'))

    except WebSocketDisconnect:
        # 客户端断开连接，清理死连接
        manager.disconnect(websocket)


@router.get("/api/history")
async def get_history(symbol: str = "BTC/USDT", interval: str = "1m"):
    """
    提供给前端的历史数据 REST API
    后端作为代理，穿透 GFW 去拉取币安数据并洗干净返回
    """
    raw_symbol = symbol.replace("/", "")
    url = f"https://api.binance.com/api/v3/klines"
    params = {
        "symbol": raw_symbol,
        "interval": interval,
        "limit": 100  # 拉取过去 100 根 K 线画图
    }

    # 代理
    proxy = "http://127.0.0.1:10809"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # 提前在后端把数据洗成 TradingView 需要的字典格式
                    clean_data = []
                    for k in data:
                        clean_data.append({
                            "time": int(k[0]) / 1000,  # TradingView 只需要秒级时间戳
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4])
                        })
                    return JSONResponse(content=clean_data)
                else:
                    return JSONResponse(content=[])
    except Exception as e:
        print(f" 拉取历史数据失败: {e}")
        return JSONResponse(content=[])