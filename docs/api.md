本文档定义了 K 线采集系统对外提供的 RESTful API 与 WebSocket 实时推送协议。

---

## 一、 REST API 接口

> **提示：** 本系统基于 FastAPI 构建，启动服务后，您也可以直接访问 `http://<host>:<port>/docs` 查看基于 OpenAPI (Swagger) 自动生成的交互式接口文档。

### 1. 查询系统支持的交易对
获取系统当前已纳管并正在轮询采集的所有交易所及其支持的现货交易对列表。

* **接口路径:** `/api/symbols`
* **请求方式:** `GET`
* **请求参数:** 无
* **响应格式:** `application/json`

**成功响应示例 (200 OK):**
```json
{
  "binance":[
    "BTC/USDT",
    "ETH/USDT"
  ],
  "okx":[
    "BTC/USDT",
    "SOL/USDT"
  ],
  "gateio":[
    "DOGE/USDT"
  ]
}
```

### 2. 查询系统运行状态
获取当前流式处理引擎的健康状况、活跃连接数以及底层队列深度。

* **接口路径:** `/api/status`
* **请求方式:** `GET`
* **请求参数:** 无
* **响应格式:** `application/json`

**成功响应示例 (200 OK):**
```json
{
  "status": "running",
  "active_ws_connections": 12,
  "queue_depth": 0,
  "exchanges_loaded":[
    "binance",
    "okx",
    "gateio"
  ]
}
```

---

## 二、 WebSocket 全双工协议

系统统一采用 WebSocket 提供**历史 K 线查询**与**实时增量数据订阅**服务，避免了 HTTP 的频繁建立连接开销，实现了真正的流式传输。

* **连接端点:** `ws://<host>:<port>/ws`
* **心跳机制:** 客户端需每隔 `30秒` 发送一次 Ping 消息，服务端超 `60秒` 未收到消息将自动断开连接，回收内存资源。

### 1. 客户端发送指令格式 (Client -> Server)

客户端发送的所有指令均为 JSON 字符串，核心字段为 `action`。

**1.1 订阅实时 K 线**
```json
{
  "action": "subscribe",
  "symbol": "BTC/USDT"
}
```

**1.2 取消订阅**
```json
{
  "action": "unsubscribe",
  "symbol": "BTC/USDT"
}
```

**1.3 查询历史 K 线 (用于图表初次渲染)**
```json
{
  "action": "get_history",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "interval": "1m"   // 支持: 1m, 5m, 15m, 1h, 4h, 1d
}
```

**1.4 发送心跳包 (Ping)**
```json
{
  "action": "ping"
}
```

### 2. 服务端推送消息格式 (Server -> Client)

服务端推送的消息通过 `type` 字段进行业务区分。

**2.1 系统通知 (订阅成功/失败等)**
```json
{
  "type": "system",
  "status": "subscribed",
  "symbol": "BTC/USDT"
}
```

**2.2 历史数据全量返回 (响应 `get_history`)**
```json
{
  "type": "history",
  "symbol": "BTC/USDT",
  "interval": "1m",
  "data":[
    {
      "time": 1710500000,
      "open": 70000.00,
      "high": 70100.00,
      "low": 69900.00,
      "close": 70050.00,
      "volume": 12.5,
      "turnover": 875625.00
    }
  ],
  "ticker": {
    "priceChangePercent": "2.54",
    "lastPrice": "70050.00"
  }
}
```

**2.3 实时 K 线增量推送 (发布-订阅模型实时广播)**
此消息会在后端引擎每次轮询获取到最新 K 线，完成 InfluxDB 固化后，通过 Redis Pub/Sub 毫秒级推送到所有订阅了该 `symbol` 的前端。
```json
{
  "type": "realtime",
  "data": {
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "interval": "1m",
    "timestamp": 1710500060000, 
    "open": 70050.00,
    "high": 70060.00,
    "low": 70040.00,
    "close": 70055.00,
    "volume": 1.2,
    "turnover": 84066.00
  }
}
```

### 3. 错误码与异常说明

| 场景 | 现象描述 | 处理建议 |
| :--- | :--- | :--- |
| **心跳超时** | 服务端主动切断 TCP 连接，无 JSON 返回 | 客户端应实现断线重连，并在 `onopen` 阶段重发 `subscribe` 订阅。 |
| **非法参数** | 接口报错或静默失败 | 请确保 `exchange` 和 `symbol` 大小写与 `/api/symbols` 返回的列表严格一致。 |
| **拉取失败** | 返回 `{"type": "error", "message": "历史数据拉取失败"}` | 通常由于上游交易所 API 触发 Rate Limit 或网络抖动，客户端可短暂延时后重试。 |
```
