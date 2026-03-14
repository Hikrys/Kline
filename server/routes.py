# app/api/routes.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from server.ws_handler import manager
from core.state import state
import json
import aiohttp
import os

router = APIRouter()


@router.get("/")
async def get_index():
    html_path = os.path.join(os.getcwd(), "static", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # 建立一个专属于这个 WebSocket 连接的 HTTP Session，用来代理拉取历史数据
    session = aiohttp.ClientSession()
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)

            action = data.get("action")
            symbol = data.get("symbol")
            interval = data.get("interval", "1m")  # 默认 1m

            if action == "subscribe" and symbol:
                await manager.subscribe(websocket, symbol)
                # 订阅成功通知
                await websocket.send_text(json.dumps({"type": "system", "status": "subscribed", "symbol": symbol}))

            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe(websocket, symbol)
                await websocket.send_text(json.dumps({"type": "system", "status": "unsubscribed", "symbol": symbol}))

            # 通过 WebSocket 查询历史数据
            elif action == "get_history" and symbol:
                raw_symbol = symbol.replace("/", "")
                url = f"https://api.binance.com/api/v3/klines"
                params = {"symbol": raw_symbol, "interval": interval, "limit": 100}
                proxy = "http://127.0.0.1:10809"

                try:
                    async with session.get(url, params=params, proxy=proxy) as resp:
                        if resp.status == 200:
                            klines = await resp.json()
                            clean_data = []
                            for k in klines:
                                clean_data.append({
                                    "time": int(k[0]) / 1000,
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5])
                                })
                            # 把历史数据打包，打上 "type": "history" 的标签发给前端
                            await websocket.send_text(json.dumps({
                                "type": "history",
                                "symbol": symbol,
                                "interval": interval,
                                "data": clean_data
                            }))
                except Exception as e:
                    print(f"WS 拉取历史数据失败: {e}")
                    await websocket.send_text(json.dumps({"type": "error", "message": "历史数据拉取失败"}))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        await session.close()


@router.get("/api/symbols")
async def get_symbols():
    """ 返回支持的交易所列表及各交易所的交易对列表"""
    return JSONResponse(content=state.symbols)

@router.get("/api/status")
async def get_status():
    """ 系统运行状态（含队列深度）"""
    return JSONResponse(content={
        "status": "running",
        "active_connections": len(manager.subscriptions),
        "queue_depth": state.queue_depth,
        "exchanges": list(state.symbols.keys())
    })