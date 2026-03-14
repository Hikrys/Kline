# storage/timeseries.py (修改头部引入和内部逻辑)
import asyncio
from typing import List
from influxdb_client import Point, WritePrecision
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from models.kline import StandardKline
from config import settings
from storage.wal import WALManager


class TimeSeriesDB:
    def __init__(self):
        self.url = settings.database.url
        self.token = settings.database.token
        self.org = settings.database.org
        self.bucket = settings.database.bucket

        self.wal = WALManager()  # 实例化 WAL 管理器
        self.client = InfluxDBClientAsync(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api()

    def _kline_to_point(self, kline: StandardKline) -> Point:
        return Point("kline") \
            .tag("exchange", kline.exchange).tag("symbol", kline.symbol).tag("interval", kline.interval) \
            .field("open", kline.open).field("high", kline.high).field("low", kline.low) \
            .field("close", kline.close).field("volume", kline.volume).field("turnover", kline.turnover) \
            .time(kline.timestamp, WritePrecision.MS)

    async def write_batch(self, klines: List[StandardKline]):
        if not klines: return
        points = [self._kline_to_point(k) for k in klines]
        try:
            await self.write_api.write(bucket=self.bucket, record=points)
            asyncio.create_task(self.replay_wal())
        except Exception as e:
            print(f" InfluxDB 写入失败，存入 WAL 日志! 错误: {e}")
            await self.wal.append(klines)

    async def replay_wal(self):
        recovered = await self.wal.read_and_clear()
        if recovered:
            points = [self._kline_to_point(k) for k in recovered]
            try:
                await self.write_api.write(bucket=self.bucket, record=points)
                print(f"WAL 日志重放成功，共恢复 {len(recovered)} 条数据！")
            except Exception:
                await self.wal.append(recovered)  # 再次失败，重新写回日志

    async def close(self):
        await self.client.close()