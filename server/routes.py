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


async def fetch_history_from_exchange(session, exchange: str, symbol: str, interval: str):
    """
    核心难点攻克：根据前端传来的交易所和周期，动态穿透去拉取真实历史数据！
    """
    proxy = settings.system.proxy_url if settings.system.use_proxy else None
    clean_data = []

    try:
        if exchange == "binance":
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": symbol.replace("/", ""), "interval": interval, "limit": 100}
            async with session.get(url, params=params, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    clean_data = [
                        {"time": int(k[0]) / 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                         "close": float(k[4]), "volume": float(k[5])} for k in data]

        elif exchange == "okx":
            # OKX 的周期参数是 1H, 1D 大写，需要转换
            okx_interval = interval.replace("h", "H").replace("d", "D")
            url = "https://aws.okx.com/api/v5/market/candles"
            params = {"instId": symbol.replace("/", "-"), "bar": okx_interval, "limit": 100}
            async with session.get(url, params=params, proxy=proxy) as resp:
                if resp.status == 200:
                    data = (await resp.json()).get("data", [])
                    data.reverse()  # OKX 返回是倒序的(最新的在最前面)，TradingView 需要正序
                    clean_data = [
                        {"time": int(k[0]) / 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                         "close": float(k[4]), "volume": float(k[5])} for k in data]

        elif exchange == "gateio":
            url = "https://api.gateio.ws/api/v4/spot/candlesticks"
            params = {"currency_pair": symbol.replace("/", "_"), "interval": interval, "limit": 100}
            async with session.get(url, params=params, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Gateio 时间戳本身就是秒，顺序是[时间, 额, 收, 高, 低, 开, 量]
                    clean_data = [{"time": int(k[0]), "open": float(k[5]), "high": float(k[3]), "low": float(k[4]),
                                   "close": float(k[2]), "volume": float(k[6])} for k in data]

    except Exception as e:
        print(f"动态拉取 {exchange} 历史数据失败: {e}")

    return clean_data


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)

            action = data.get("action")
            symbol = data.get("symbol")
            exchange = data.get("exchange", "binance")
            interval = data.get("interval", "1m")

            if action == "subscribe" and symbol:
                await manager.subscribe(websocket, symbol)

            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe(websocket, symbol)

            elif action == "get_history" and symbol:
                history_data = await fetch_history_from_exchange(session, exchange, symbol, interval)

                await websocket.send_text(json.dumps({
                    "type": "history",
                    "symbol": symbol,
                    "interval": interval,
                    "data": history_data
                }))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        await session.close()