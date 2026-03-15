# app/models/kline.py
from pydantic import BaseModel, Field
from typing import Literal


class StandardKline(BaseModel):
    """
    统一的 K 线数据模型 (相当于 Go 里的 type StandardKline struct)
    不管 Binance 还是 OKX 返回什么破烂格式，进入系统必须变成这个样子
    """
     # 清洗数据
    exchange: Literal["binance", "okx", "gateio"] = Field(..., description="交易所名称")
    # Field(...) 表示这个字段是必填项，不可为空
    symbol: str = Field(..., description="统一的交易对名称, 例如 BTC/USDT")
    interval: str = Field(..., description="K线周期, 例如 1m")
    timestamp: int = Field(..., description="K线开盘时间戳(毫秒)")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")
    turnover: float = Field(..., description="成交额")

    class Config:
        json_dumps = "orjson.dumps"
        json_loads = "orjson.loads"