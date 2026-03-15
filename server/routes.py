# server/routes.py
import orjson
import asyncio
import aiohttp
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Dict, Any, Tuple

from server.ws_handler import manager
from core.state import state
from config import settings

router = APIRouter()


@router.get("/")
async def get_index():
    html_path = os.path.join(os.getcwd(), "web", "index.html")
    with open(html_path, "r", encoding="utf-8") as f: return HTMLResponse(content=f.read())


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


async def fetch_history_from_exchange(
    session: aiohttp.ClientSession,
    exchange: str,
    symbol: str,
    interval: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    根据前端传来的交易所和周期，动态穿透去拉取真实历史数据和 24H 涨跌幅
    """
    proxy = settings.system.proxy_url if settings.system.use_proxy else None
    clean_data = []
    ticker_data = {"priceChangePercent": "0.00", "lastPrice": "0.00"}

    try:
        if exchange == "binance":
            kline_url = "https://api.binance.com/api/v3/klines"
            ticker_url = "https://api.binance.com/api/v3/ticker/24hr"
            raw_symbol = symbol.replace("/", "")

            # 并发获取 K线 和 24H 涨跌幅
            async with session.get(kline_url, params={"symbol": raw_symbol, "interval": interval, "limit": 100},
                                   proxy=proxy) as resp1, \
                    session.get(ticker_url, params={"symbol": raw_symbol}, proxy=proxy) as resp2:
                if resp1.status == 200:
                    data = await resp1.json()
                    clean_data = [
                        {"time": int(k[0]) / 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                         "close": float(k[4]), "volume": float(k[5]), "turnover": float(k[7])} for k in data]
                if resp2.status == 200:
                    t_data = await resp2.json()
                    ticker_data = {"priceChangePercent": t_data.get("priceChangePercent", "0.00"),
                                   "lastPrice": t_data.get("lastPrice", "0.00")}

        elif exchange == "okx":
            okx_interval = interval.replace("h", "H").replace("d", "D")
            url = "https://aws.okx.com/api/v5/market/candles"
            ticker_url = "https://aws.okx.com/api/v5/market/ticker"
            raw_symbol = symbol.replace("/", "-")

            async with session.get(url, params={"instId": raw_symbol, "bar": okx_interval, "limit": 100},
                                   proxy=proxy) as resp1, \
                    session.get(ticker_url, params={"instId": raw_symbol}, proxy=proxy) as resp2:
                if resp1.status == 200:
                    data = (await resp1.json()).get("data", [])
                    data.reverse()  # OKX 是倒序的，需要反转
                    clean_data = [
                        {"time": int(k[0]) / 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                         "close": float(k[4]), "volume": float(k[5]), "turnover": float(k[6])} for k in data]
                if resp2.status == 200:
                    t_data = (await resp2.json()).get("data", [{}])[0]
                    open24 = float(t_data.get("sod24", 1) or 1)
                    last = float(t_data.get("last", 0))
                    pct = ((last - open24) / open24) * 100 if open24 else 0.0
                    ticker_data = {"priceChangePercent": f"{pct:.2f}", "lastPrice": str(last)}

        elif exchange == "gateio":
            url = "https://api.gateio.ws/api/v4/spot/candlesticks"
            ticker_url = "https://api.gateio.ws/api/v4/spot/tickers"
            raw_symbol = symbol.replace("/", "_")

            async with session.get(url, params={"currency_pair": raw_symbol, "interval": interval, "limit": 100},
                                   proxy=proxy) as resp1, \
                    session.get(ticker_url, params={"currency_pair": raw_symbol}, proxy=proxy) as resp2:
                if resp1.status == 200:
                    data = await resp1.json()
                    clean_data = [{"time": int(k[0]), "open": float(k[5]), "high": float(k[3]), "low": float(k[4]),
                                   "close": float(k[2]), "volume": float(k[6]), "turnover": float(k[1])} for k in data]
                if resp2.status == 200:
                    t_data = await resp2.json()
                    if t_data:
                        ticker_data = {"priceChangePercent": t_data[0].get("change_percentage", "0.00"),
                                       "lastPrice": t_data[0].get("last", "0.00")}

    except Exception as e:
        print(f"动态拉取 {exchange} 历史数据失败: {e}")

    return clean_data, ticker_data


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    proxy = settings.system.proxy_url if settings.system.use_proxy else None
    connector = aiohttp.TCPConnector(ssl=False)
    session = aiohttp.ClientSession(connector=connector)

    try:
        while True:
            # 60秒心跳超时保护
            data_str = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            data = orjson.loads(data_str)

            action = data.get("action")
            symbol = data.get("symbol")
            interval = data.get("interval", "1m")
            exchange = data.get("exchange", "binance")

            if action == "subscribe" and symbol:
                await manager.subscribe(websocket, symbol)

            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe(websocket, symbol)

            elif action == "ping":
                await websocket.send_text(orjson.dumps({"type": "pong"}))

            elif action == "get_history" and symbol:
                # 调用多交易所代理请求，拿到洗干净的历史数据和真实涨跌幅！
                history_data, ticker_data = await fetch_history_from_exchange(session, exchange, symbol, interval)

                await websocket.send_text(orjson.dumps({
                    "type": "history",
                    "symbol": symbol,
                    "interval": interval,
                    "data": history_data,
                    "ticker": ticker_data
                }))

    except asyncio.TimeoutError:
        print("WebSocket 心跳超时，自动清理孤立连接！")
        manager.disconnect(websocket)
        await websocket.close()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        await session.close()