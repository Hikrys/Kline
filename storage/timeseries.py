# storage/timeseries.py
import asyncio
import aiofiles
import os
from typing import List
from influxdb_client import Point, WritePrecision
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from models.kline import StandardKline
from config import settings  # 引入全局配置！


class TimeSeriesDB:
    def __init__(self):
        self.url = settings.database.url
        self.token = settings.database.token
        self.org = settings.database.org
        self.bucket = settings.database.bucket

        self.wal_file = "wal.log"
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
            .time(kline.timestamp, WritePrecision.MS)

    async def write_batch(self, klines: List[StandardKline]):
        if not klines: return
        points = [self._kline_to_point(k) for k in klines]
        try:
            await self.write_api.write(bucket=self.bucket, record=points)
            asyncio.create_task(self.replay_wal())
        except Exception as e:
            print(f"!!!InfluxDB 写入失败，存入 WAL 日志! 错误: {e}")
            await self._write_wal(klines)

    async def _write_wal(self, klines: List[StandardKline]):
        async with aiofiles.open(self.wal_file, mode='a') as f:
            for kline in klines:
                await f.write(kline.model_dump_json() + "\n")

    async def replay_wal(self):
        if not os.path.exists(self.wal_file) or os.path.getsize(self.wal_file) == 0:
            return
        try:
            async with aiofiles.open(self.wal_file, mode='r') as f:
                lines = await f.readlines()
            recovered = [StandardKline.model_validate_json(line) for line in lines if line.strip()]
            points = [self._kline_to_point(k) for k in recovered]
            await self.write_api.write(bucket=self.bucket, record=points)

            async with aiofiles.open(self.wal_file, mode='w') as f:
                await f.truncate()
            print(f"WAL 日志重放成功，共恢复 {len(recovered)} 条数据！")
        except Exception as e:
            pass

    async def close(self):
        await self.client.close()