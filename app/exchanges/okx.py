# app/exchanges/okx.py
import aiohttp
from typing import List, Optional
from app.exchanges.base import BaseExchange
from app.models.kline import StandardKline


class OkxAPI(BaseExchange):
    def __init__(self):
        super().__init__()
        self.exchange_name = "okx"
        self.base_url = "https://aws.okx.com"
        self.proxy = "http://127.0.0.1:10809"

    async def fetch_symbols(self, session: aiohttp.ClientSession) -> List[str]:
        mirror_urls = [
            "https://aws.okx.com",
            "https://www.okx.com",
            "https://www.okx.cab"
        ]

        for base_url in mirror_urls:
            url = f"{base_url}/api/v5/public/instruments"
            params = {"instType": "SPOT"}
            try:
                # 五秒超时，域名失效，立刻切换下一个
                async with session.get(url, params=params, proxy=self.proxy, timeout=5) as response:
                    if response.status == 200:
                        self.base_url = base_url  # 这个打通的域名，后面拉 K 线就用这个
                        json_data = await response.json()
                        symbols = []
                        for item in json_data.get("data", []):
                            if item.get("state") == "live":
                                symbols.append(f"{item.get('baseCcy')}/{item.get('quoteCcy')}")
                        return symbols
            except Exception as e:
                print(f" 尝试 OKX 域名 {base_url} 失败，切换下一个...")
                continue

        print(" 所有 OKX 域名均无法连接，请检查代理节点是否屏蔽了 OKX")
        return []

    async def fetch_kline(self, session: aiohttp.ClientSession, symbol: str, interval: str) -> Optional[StandardKline]:
        """
        获取单根 K 线数据
        """
        # 转回 OKX 的格式 "BTC-USDT"
        raw_symbol = symbol.replace("/", "-")
        url = f"{self.base_url}/api/v5/market/candles"

        # OKX 的周期参数叫 bar
        params = {
            "instId": raw_symbol,
            "bar": interval,
            "limit": 1
        }

        try:
            async with session.get(url, params=params, proxy=self.proxy) as response:
                if response.status != 200:
                    return None
                json_data = await response.json()
                data_list = json_data.get("data", [])

                if not data_list:
                    return None

                # OKX 格式:[ts, open, high, low, close, vol, volCcy(turnover), volCcyQuote, confirm]
                k = data_list[0]

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
                    turnover=float(k[6])
                )
        except Exception as e:
            # 捕获异常，防止影响全局并发
            return None