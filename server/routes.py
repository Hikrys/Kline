# server/routes.py
import json
import aiohttp
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from server.ws_handler import manager
from core.state import state
from config import settings

router = APIRouter()


@router.get("/")
async def get_index():
    html_path = os.path.join(os.getcwd(), "web", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@router.get("/api/symbols")
async def get_symbols():
    return JSONResponse(content=state.symbols)


@router.get("/api/status")
async def get_status():
    return JSONResponse(content={
        "status": "running",
        "active_ws_connections": len(manager.subscriptions),
        "queue_depth": state.queue_depth,
        "exchanges_loaded": list(state.symbols.keys())
    })


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    # 获取配置里的代理
    proxy = settings.system.proxy_url if settings.system.use_proxy else None
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)

            action = data.get("action")
            symbol = data.get("symbol")
            interval = data.get("interval", "1m")

            if action == "subscribe" and symbol:
                await manager.subscribe(websocket, symbol)

            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe(websocket, symbol)

            elif action == "get_history" and symbol:
                raw_symbol = symbol.replace("/", "")

                # 同时并发请求 历史K线数据和24小时涨跌幅数据
                kline_url = f"https://api.binance.com/api/v3/klines"
                ticker_url = f"https://api.binance.com/api/v3/ticker/24hr"

                params = {"symbol": raw_symbol, "interval": interval, "limit": 100}
                ticker_params = {"symbol": raw_symbol}

                try:
                    # 并发拉取两个接口，节省时间！
                    async with session.get(kline_url, params=params, proxy=proxy) as resp1, \
                            session.get(ticker_url, params=ticker_params, proxy=proxy) as resp2:

                        klines = await resp1.json() if resp1.status == 200 else []
                        ticker = await resp2.json() if resp2.status == 200 else {}

                        clean_data = [{
                            "time": int(k[0]) / 1000, "open": float(k[1]),
                            "high": float(k[2]), "low": float(k[3]),
                            "close": float(k[4]), "volume": float(k[5])
                        } for k in klines]

                        # 把历史 K 线和 24h 涨跌幅一起打包发给前端
                        await websocket.send_text(json.dumps({
                            "type": "history",
                            "symbol": symbol,
                            "interval": interval,
                            "data": clean_data,
                            "ticker": {
                                "priceChangePercent": ticker.get("priceChangePercent", "0.00"),
                                "lastPrice": ticker.get("lastPrice", "0.00")
                            }
                        }))
                except Exception as e:
                    print(f"!!!WS 拉取历史数据失败: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        await session.close()