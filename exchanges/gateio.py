# app/exchanges/gateio.py
import aiohttp
from typing import List, Optional
from exchanges.base import BaseExchange
from models.kline import StandardKline


class GateioAPI(BaseExchange):
    def __init__(self):
        super().__init__()
        self.exchange_name = "gateio"
        self.base_url = "https://api.gateio.ws"
        self.proxy = "http://127.0.0.1:10809"

    async def fetch_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        url = f"{self.base_url}/api/v4/spot/currency_pairs"
        try:
            # 加个 15 秒超时，防止死等
            async with session.get(url, proxy=self.proxy, timeout=15) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"⚠️ Gateio 被拦截! 状态码: {response.status}, 详情: {error_text[:100]}")
                    return []

                data = await response.json()
                symbols = []
                for item in data:
                    if item.get("trade_status") == "tradable":
                        base = item.get("base")
                        quote = item.get("quote")
                        symbols.append(f"{base}/{quote}")
                return symbols
        except Exception as e:
            print(f"获取 Gate.io 交易对异常: {e}")
            return

    async def fetch_kline(self, session: aiohttp.ClientSession, symbol: str, interval: str) -> Optional[StandardKline]:
        # 转回 Gate 的格式 "BTC_USDT"
        raw_symbol = symbol.replace("/", "_")
        url = f"{self.base_url}/api/v4/spot/candlesticks"

        params = {
            "currency_pair": raw_symbol,
            "interval": interval,
            "limit": 1
        }

        try:
            async with session.get(url, params=params, proxy=self.proxy) as response:
                if response.status != 200:
                    return None
                data = await response.json()

                if not data:
                    return None

                # Gate 格式: 时间(秒), 交易额, 收盘价, 最高价, 最低价, 开盘价, 交易量
                k = data[0]

                return StandardKline(
                    exchange=self.exchange_name,
                    symbol=symbol,
                    interval=interval,
                    # 这里Gate给的是秒，根据文档的要求是毫秒级的时间戳,所以 x1000 补齐
                    timestamp=int(k[0]) * 1000,
                    turnover=float(k[1]),
                    close=float(k[2]),
                    high=float(k[3]),
                    low=float(k[4]),
                    open=float(k[5]),
                    volume=float(k[6])
                )
        except Exception as e:
            return None