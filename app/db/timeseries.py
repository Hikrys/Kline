# app/db/timeseries.py
import json
import asyncio
import aiofiles
import os
from typing import List
from influxdb_client import Point, WritePrecision
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from app.models.kline import StandardKline


class TimeSeriesDB:
    def __init__(self):
        self.url = "http://localhost:8086"
        self.token = "my-super-secret-auth-token-for-kline"
        self.org = "kline_org"
        self.bucket = "kline_bucket"

        # WAL 预写式日志的文件路径
        self.wal_file = "wal.log"

        # 实例化官方的异步客户端
        self.client = InfluxDBClientAsync(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api()

    def _kline_to_point(self, kline: StandardKline) -> Point:

        return Point("kline") \
            .tag("exchange", kline.exchange) \
            .tag("symbol", kline.symbol) \
            .tag("interval", kline.interval) \
            .field("open", kline.open) \
            .field("high", kline.high) \
            .field("low", kline.low) \
            .field("close", kline.close) \
            .field("volume", kline.volume) \
            .field("turnover", kline.turnover) \
            .time(kline.timestamp, WritePrecision.MS)  # 毫秒精度

    async def write_batch(self, klines: List[StandardKline]):
        """
        批量异步写入数据库。如果数据库挂了，就写到本地 WAL 文件里。
        """
        if not klines:
            return

        points = [self._kline_to_point(k) for k in klines]

        try:
            # 尝试写入 InfluxDB
            await self.write_api.write(bucket=self.bucket, record=points)
            # print(f" 成功批量写入 {len(klines)} 条 K 线数据到 InfluxDB!")

            # 如果写入成功，我们可以顺便检查一下有没有积压的 WAL 日志需要重放
            asyncio.create_task(self.replay_wal())

        except Exception as e:
            print(f" InfluxDB 写入失败，触发断网保护，存入 WAL 日志! 错误: {e}")
            await self._write_wal(klines)

    async def _write_wal(self, klines: List[StandardKline]):
        """
        WAL (Write-Ahead Log) 机制：用 aiofiles 异步追加到本地文件
        """
        # aiofiles 能保证即使在超高并发下，写文件也不会阻塞主事件循环
        async with aiofiles.open(self.wal_file, mode='a') as f:
            for kline in klines:
                # 把模型转成 JSON 字符串，并加上换行符存进去 (JSONL 格式)
                line = kline.model_dump_json() + "\n"
                await f.write(line)

    async def replay_wal(self):
        """
        重放 WAL 日志：读取本地日志并重新写入数据库，成功后清空文件
        """
        if not os.path.exists(self.wal_file) or os.path.getsize(self.wal_file) == 0:
            return

        print(" 发现 WAL 日志，正在重放历史失败数据...")
        try:
            async with aiofiles.open(self.wal_file, mode='r') as f:
                lines = await f.readlines()

            # 把每一行 JSON 还原成 StandardKline 对象
            recovered_klines = [StandardKline.model_validate_json(line) for line in lines if line.strip()]

            # 重新把它们转成 Point
            points = [self._kline_to_point(k) for k in recovered_klines]

            # 再次尝试写入！
            await self.write_api.write(bucket=self.bucket, record=points)

            # 重放成功，清空 WAL 文件！
            async with aiofiles.open(self.wal_file, mode='w') as f:
                await f.truncate()
            print(f" WAL 日志重放成功，共恢复 {len(recovered_klines)} 条数据！")

        except Exception as e:
            print(f" WAL 重放依然失败，等待下次尝试: {e}")

    async def close(self):
        """优雅关闭客户端连接"""
        await self.client.close()