```markdown
# 比特鹰 - 多交易所 K 线实时采集与流式推送系统

## 项目概述
本项目是一个高性能的分布式 K 线数据采集与实时推送引擎。系统深度对接了 **Binance, OKX, Gate.io** 三大中心化交易所，实现了数千个现货交易对的自动发现、全量分钟级 K 线无缝采集、时序数据库固化，以及面向前端的超低延迟 WebSocket 全双工流式推送。

严格遵循领域驱动设计 (DDD) 思想，实现了 **采集、存储、推送三层的完美解耦**，具备极强的高并发处理能力与断网容灾自愈能力。

##  核心技术栈
* **后端引擎:** Python 3.13+ (Asyncio 异步高并发架构)
* **Web 框架:** FastAPI + Uvicorn
* **性能加速:** `uvloop` (Linux下替换默认事件循环) + `orjson` (Rust级序列化引擎)
* **时序存储:** InfluxDB v2
* **消息总线:** Redis Pub/Sub (分布式集群数据中枢)
* **前端展示:** TradingView Lightweight Charts (原生 HTML5 + JS, 无框架依赖)

---

## 核心架构与技术亮点

### 1. 匀速滑动限流并发轮询 
放弃了低效的阻塞请求，采用 `asyncio.TaskGroup` 管理上千个并发协程。通过自主设计的 `RateLimiter`，将上千个 API 请求极其均匀地平滑打散在 60 秒的窗口内，完美绕过各大交易所的 Rate Limit 封禁防护墙，实现全量交易对 **0 漏抓**。

### 2. 多交易所适配层与容灾自愈 
* 实现了 `BaseExchange` 抽象基类，新增交易所只需继承实现两个方法，无需修改核心逻辑，高度符合开闭原则 (OCP)。
* **API 穿透:** 针对 OKX 等海外节点网络波动，内置多路备用域名（如 `aws.okx.com`）轮询重试机制，实现网络故障自动转移。

### 3. 时序数据库双写与 WAL 灾备 
* 强依赖 InfluxDB 的 `Tag` 与 `Timestamp` 机制，天然实现时间序列的线性存储与自动去重。
* 设计了严格的 `WALManager` (Write-Ahead Log)。当检测到数据库断连时，系统将数据异步 Append 至本地 `wal.log`；待数据库恢复后，守护进程自动读取并无缝重放历史数据，确保核心金融数据 **0 丢失**。

### 4. 基于 Redis Pub/Sub 的无状态集群 
彻底摒弃了内存字典管理 WebSocket 订阅者的传统做法。采集引擎将最新 K 线发布至 Redis 消息总线，FastAPI 服务作为订阅者监听并分发。此设计使得 Web 服务**完全无状态**，可随时横向扩展多个容器实例，轻松应对海量并发订阅。

---


## API 接口与交互协议

本项目严格遵循前后端分离与全双工通信规范。为了保持 README 的整洁，极其详尽的 API 调用示例、
参数说明、WebSocket 报文定义及错误码字典，已单独抽离至专属文档：(./docs/api.md)**

## 项目目录结构说明

```text
kline_system/
├── config.yaml               # 全局配置文件 (数据库、Redis、代理)
├── config.py                 # Pydantic 强类型配置映射与校验
├── main.py                   # 应用启动入口 & 守护进程挂载
├── Dockerfile                # 多阶段精简镜像构建脚本
├── docker-compose.yml        # 一站式微服务编排配置
│
├── engine/                   # 核心引擎层
│   ├── queue.py              # 异步消息队列封装
│   ├── rate_limiter.py       # 匀速限流器
│   └── scheduler.py          # 轮询调度与并发采集引擎
│
├── storage/                  # 数据持久层
│   ├── timeseries.py         # InfluxDB 交互层
│   └── wal.py                # WAL 预写式灾备日志管理
│
├── server/                   # Web 服务层
│   ├── app.py                # FastAPI 实例工厂
│   ├── routes.py             # REST API 与 WS 协议路由
│   └── ws_handler.py         # 基于 Redis 的分布式 WS 广播中心
│
├── exchanges/                # 交易所适配层
│   ├── base.py               # BaseExchange 抽象基类
│   ├── binance.py / okx.py / gateio.py
│
├── models/                   # 数据模型层
│   └── kline.py              # Pydantic 强类型标准 K 线模型
│
├── core/                     # 全局状态层】
│   └── state.py              # 内存状态机 (缓存交易对与队列深度)
│
├── docs/                     # 交付验收文档
│   └── api.md                # 详细的 API 与 WebSocket 协议规范
│
└── web/                      # 前端静态资源
    ├── index.html            # 主视图
    ├── style.css             # 暗黑风样式
    └── app.js                # 图表渲染与 WS 通信逻辑
```

---

## 本地开发与启动指引

### 方式一：容器化一键部署 
本项目提供生产级构建配置，自动执行多阶段依赖隔离，无需在宿主机安装任何 Python 环境。

```bash
# 1. 在项目根目录执行打包与启动
docker-compose up --build -d

# 2. 打开浏览器访问监控前端
http://127.0.0.1:8089 
```

### 方式二：源码本地运行
1. **环境准备**: Python 3.13+。
2. **基础设施**: 确保本地已启动 InfluxDB (端口 8086) 与 Redis (端口 6379)。
3. **依赖安装**:
   ```bash
   pip install -r requirements.txt
   ```
4. **服务启动**:
   ```bash
   python main.py
   ```

---
