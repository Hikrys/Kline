# 第一阶段：构建依赖
FROM python:3.13-slim AS builder

# 确保控制台输出不被缓冲，方便看日志
ENV PYTHONUNBUFFERED=1

# 安装 C 语言编译工具 为 orjson 等高性能库提供编译环境
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential

# 在第一阶段创建一个隔离的虚拟环境
RUN python -m venv /opt/venv
# 将环境变量指向虚拟环境
ENV PATH="/opt/venv/bin:$PATH"

# 复制清单并安装依赖到虚拟环境中
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim

WORKDIR /app

# 把第一阶段编译好的整个虚拟环境拷过来
COPY --from=builder /opt/venv /opt/venv

# 告诉系统，运行命令时去虚拟环境里找
ENV PATH="/opt/venv/bin:$PATH"

# 把所有源码和 web 文件夹拷贝进容器
COPY . .

# 暴露 FastAPI 的 8000 端口
EXPOSE 8000

# 启动引擎！
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]