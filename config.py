# config.py
import yaml
import os
from pydantic import BaseModel

class SystemConfig(BaseModel):
    use_proxy: bool
    proxy_url: str
    debug: bool

class DatabaseConfig(BaseModel):
    url: str
    token: str
    org: str
    bucket: str

class ServerConfig(BaseModel):
    host: str
    port: int

class RedisConfig(BaseModel):
    url: str

class AppConfig(BaseModel):
    system: SystemConfig
    database: DatabaseConfig
    server: ServerConfig
    redis: RedisConfig

def load_config() -> AppConfig:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # 用 Pydantic 做严格类型校验
    return AppConfig(**data)

# 导出一个全局单例配置
settings = load_config()