# app/core/state.py
from typing import Dict, List

class AppState:
    """
    全局状态机：用于给 REST API 提供系统运行状态和交易对列表
    """
    def __init__(self) -> None:
        # 存储每个交易所拉取到的全量交易对
        self.symbols: Dict[str, List[str]] = {
            "binance":[],
            "okx": [],
            "gateio":[]
        }
        # 记录当前队列深度
        self.queue_depth: int = 0

# 导出一个单例
state = AppState()