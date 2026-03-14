# app/services/ws_handler.py
from fastapi import WebSocket
from typing import Dict, Set
from models.kline import StandardKline
import orjson


class ConnectionManager:
    """
    WebSocket 连接管理器 (相当于 Go IM 项目里的 Hub/ClientManager)
    负责维护谁订阅了什么交易对，以及向他们广播最新价格。
    """

    def __init__(self):
        # 内存订阅字典：Key 是交易对(如 BTC/USDT)，Value 是订阅了这个对的所有 WebSocket 连接集合
        # 相当于 Go 里的 map[string]map[*websocket.Conn]bool
        self.subscriptions: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        # 接受客户端的连接
        await websocket.accept()

    def disconnect(self, websocket: WebSocket):
        # 客户端断开时，从所有订阅的集合中移除它
        for symbol, connections in self.subscriptions.items():
            if websocket in connections:
                connections.remove(websocket)

    async def subscribe(self, websocket: WebSocket, symbol: str):
        # 处理客户端发送订阅请求
        if symbol not in self.subscriptions:
            self.subscriptions[symbol] = set()
        self.subscriptions[symbol].add(websocket)
        print(f"🔗 客户端订阅了: {symbol} (当前该对共有 {len(self.subscriptions[symbol])} 个订阅)")

    async def unsubscribe(self, websocket: WebSocket, symbol: str):
        # 取消订阅
        if symbol in self.subscriptions and websocket in self.subscriptions[symbol]:
            self.subscriptions[symbol].remove(websocket)

    async def broadcast_kline(self, kline: StandardKline):
        if kline.symbol in self.subscriptions:
            connections = self.subscriptions[kline.symbol]
            if not connections:
                return

            # 把 K 线数据包装一层，标明这是实时增量数据
            payload = {
                "type": "realtime",
                "data": kline.model_dump()
            }
            json_bytes = orjson.dumps(payload)
            json_str = json_bytes.decode('utf-8')

            for connection in list(connections):
                try:
                    await connection.send_text(json_str)
                except Exception as e:
                    self.disconnect(connection)


# 导出一个全局单例，供整个应用使用
manager = ConnectionManager()