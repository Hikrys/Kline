# server/ws_handler.py
import json
import asyncio
import redis.asyncio as aioredis
from fastapi import WebSocket
from typing import Dict, Set
from config import settings


class ConnectionManager:
    """
    分布式 WebSocket 连接管理器
    """
    def __init__(self):
        # 本地内存字典，只存连到【当前容器】的用户
        self.subscriptions: Dict[str, Set[WebSocket]] = {}
        # 连接 Redis
        self.redis = aioredis.from_url(settings.redis.url)
        self.pubsub = self.redis.pubsub()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    def disconnect(self, websocket: WebSocket):
        """清理死连接"""
        for symbol, connections in self.subscriptions.items():
            if websocket in connections:
                connections.remove(websocket)

    async def subscribe(self, websocket: WebSocket, symbol: str):
        if symbol not in self.subscriptions:
            self.subscriptions[symbol] = set()
        self.subscriptions[symbol].add(websocket)

    async def unsubscribe(self, websocket: WebSocket, symbol: str):
        if symbol in self.subscriptions and websocket in self.subscriptions[symbol]:
            self.subscriptions[symbol].remove(websocket)

    async def broadcast_local(self, message_str: str, symbol: str):
        """收到 Redis 的广播后，转发给连在本机的对应用户"""
        if symbol in self.subscriptions:
            connections = self.subscriptions[symbol]
            dead_connections = set()
            for connection in list(connections):
                try:
                    await connection.send_text(message_str)
                except Exception:
                    dead_connections.add(connection)

            # 自动清理发送失败的孤立连接
            for dead in dead_connections:
                self.disconnect(dead)

    async def listen_to_redis(self):
        """
        后台守护进程：持续监听 Redis 频道的全局广播
        """
        await self.pubsub.subscribe("kline:broadcast")
        print("[分布式中枢] 已启动 Redis 订阅，等待引擎广播...")
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    # 解析 Redis 发来的数据
                    data_str = message["data"].decode("utf-8")
                    data = json.loads(data_str)
                    # 提取出这是哪个币的数据
                    symbol = data.get("data", {}).get("symbol")
                    if symbol:
                        # 触发本机分发！
                        await self.broadcast_local(data_str, symbol)
        except Exception as e:
            print(f"Redis 监听异常: {e}")


manager = ConnectionManager()