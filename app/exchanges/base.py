# app/exchanges/base.py
import abc
from typing import List
from app.models.kline import StandardKline


class BaseExchange(abc.ABC):
    def __init__(self):
        # 交易所的名字，子类必须重写
        self.exchange_name: str = "base"

        # 基础 URL，子类必须重写
        self.base_url: str = ""

    @abc.abstractmethod
    async def fetch_symbols(self) -> List[str]:
        """
        获取该交易所所有可用的现货交易对
        返回值示例:["BTC/USDT", "ETH/USDT"]
        """
        pass

    @abc.abstractmethod
    async def fetch_kline(self, symbol: str, interval: str) -> StandardKline | None:
        """
        获取某个交易对最新的一根 K 线数据
        返回值: 我们刚定义的统一数据模型 StandardKline
        """
        pass