# app/exchanges/binance.py
import aiohttp
from typing import List, Optional
from app.exchanges.base import BaseExchange
from app.models.kline import StandardKline


class BinanceAPI(BaseExchange):
    def __init__(self):
        super().__init__()
        self.exchange_name = "binance"
        self.base_url = "https://api.binance.com"
        self.proxy = "http://127.0.0.1:10809"

    async def fetch_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        """
        获取币安所有现货交易对
        """
        url = f"{self.base_url}/api/v3/exchangeInfo"

        # async with 相当于 Go 里的 defer resp.Body.Close()，自动释放连接
        async with session.get(url, proxy=self.proxy) as response:
            data = await response.json()
            symbols = []

            # 遍历币安返回的巨大 JSON 里的 symbols 列表
            for item in data.get("symbols", []):
                # 兼容币安新旧 API 的现货权限判断
                permissions = item.get("permissions", [])
                permission_sets = item.get("permissionSets", [])
                # any(...) 相当于 Go 里写了个 for 循环遍历切片去判断有没有 "SPOT"
                is_spot = "SPOT" in permissions or any("SPOT" in p_set for p_set in permission_sets)
                # 状态是 TRADING 且包含 SPOT 现货权限的，才进行接收
                if item.get("status") == "TRADING" and is_spot:
                    base = item.get("baseAsset")
                    quote = item.get("quoteAsset")
                    symbols.append(f"{base}/{quote}")

            return symbols

    async def fetch_kline(self, session: aiohttp.ClientSession, symbol: str, interval: str) -> Optional[StandardKline]:
        """
        获取单根 K 线数据
        """
        # 我们传进来的是 "BTC/USDT"，请求币安时得转回 "BTCUSDT"
        raw_symbol = symbol.replace("/", "")
        url = f"{self.base_url}/api/v3/klines"

        # 请求参数：限制只拉取最新的一根 (limit=1)
        params = {
            "symbol": raw_symbol,
            "interval": interval,
            "limit": 1
        }

        async with session.get(url, params=params, proxy=self.proxy) as response:
            if response.status != 200:
                # 相当于 Go 里的 if err != nil { return nil, err }
                return None

            data = await response.json()
            if not data:
                return None

            # [0:开盘时间, 1:开盘价, 2:最高价, 3:最低价, 4:收盘价, 5:成交量, 6:收盘时间, 7:成交额]
            k = data[0]

            # 组装成我们自己的 Pydantic 结构体并返回！
            return StandardKline(
                exchange=self.exchange_name,
                symbol=symbol,
                interval=interval,
                timestamp=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                turnover=float(k[7])
            )