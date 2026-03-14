# engine/rate_limit.py
import asyncio

class RateLimiter:
    """
    匀速调度限流器 (平滑分布请求，避免触发 Rate Limit)
    """
    def __init__(self, total_requests: int, window_seconds: float = 60.0):
        # 计算每个请求之间的完美间隔时间
        self.delay = window_seconds / total_requests if total_requests > 0 else window_seconds

    async def wait(self):
        """在每次发起请求前调用此方法，实现均匀等待"""
        await asyncio.sleep(self.delay)