# storage/wal.py
import aiofiles
import os
from typing import List
from models.kline import StandardKline


class WALManager:
    """
    Write-Ahead Log 预写式日志管理器
    负责在数据库断网时，将数据异步追加到本地文件
    """

    def __init__(self, filepath: str = "wal.log"):
        self.filepath = filepath

    async def append(self, klines: List[StandardKline]):
        """异步追加写入"""
        async with aiofiles.open(self.filepath, mode='a') as f:
            for kline in klines:
                await f.write(kline.model_dump_json() + "\n")

    async def read_and_clear(self) -> List[StandardKline]:
        """读取历史失败数据，并清空文件"""
        if not os.path.exists(self.filepath) or os.path.getsize(self.filepath) == 0:
            return []

        async with aiofiles.open(self.filepath, mode='r') as f:
            lines = await f.readlines()

        # 清空文件
        async with aiofiles.open(self.filepath, mode='w') as f:
            await f.truncate()

        return [StandardKline.model_validate_json(line) for line in lines if line.strip()]