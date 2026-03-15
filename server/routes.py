# server/routes.py
import json
import asyncio
import aiohttp
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from server.ws_handler import manager
from core.state import state
from config import settings

router = APIRouter()


# ... (get_index, get_symbols, get_status 这三个 REST 接口保持不变) ...
@router.get("/")
async def get_index():
    html_path = os.path.join(os.getcwd(), "web", "index.html")
    with open(html_path, "r", encoding="utf-8") as f: return HTMLResponse(content=f.read())


@router.get("/api/symbols")
async def get_symbols():
    return JSONResponse(content=state.symbols)


@router.get("/api/status")
async def get_status():
    return JSONResponse(content={"status": "running", "active_ws_connections": len(manager.subscriptions),
                                 "queue_depth": state.queue_depth, "exchanges_loaded": list(state.symbols.keys())})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    proxy = settings.system.proxy_url if settings.system.use_proxy else None
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    try:
        while True:
            # 心跳机制：如果 60 秒客户端不发任何消息，触发 TimeoutError 异常
            data_str = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            data = json.loads(data_str)

            action = data.get("action")
            symbol = data.get("symbol")
            interval = data.get("interval", "1m")
            exchange = data.get("exchange", "binance")

            if action == "subscribe" and symbol:
                await manager.subscribe(websocket, symbol)
            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe(websocket, symbol)

            # 响应客户端的 Ping 心跳包
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif action == "get_history" and symbol:
                kline_url = f"https://api.binance.com/api/v3/klines"
                ticker_url = f"https://api.binance.com/api/v3/ticker/24hr"
                params = {"symbol": symbol.replace("/", ""), "interval": interval, "limit": 100}
                ticker_params = {"symbol": symbol.replace("/", "")}

                try:
                    async with session.get(kline_url, params=params, proxy=proxy) as resp1, \
                            session.get(ticker_url, params=ticker_params, proxy=proxy) as resp2:
                        klines = await resp1.json() if resp1.status == 200 else []
                        ticker = await resp2.json() if resp2.status == 200 else {}
                        clean_data = [
                            {"time": int(k[0]) / 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                             "close": float(k[4]), "volume": float(k[5])} for k in klines]

                        await websocket.send_text(json.dumps({
                            "type": "history", "symbol": symbol, "interval": interval, "data": clean_data,
                            "ticker": {"priceChangePercent": ticker.get("priceChangePercent", "0.00"),
                                       "lastPrice": ticker.get("lastPrice", "0.00")}
                        }))
                except Exception as e:
                    pass

    except asyncio.TimeoutError:
        print(" WebSocket 心跳超时，自动清理孤立连接！")
        manager.disconnect(websocket)
        await websocket.close()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        await session.close()