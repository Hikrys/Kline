FROM python:3.13-slim AS builder

# 设置工作目录
WORKDIR /app

# 复制依赖清单并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 把其他代码也拷入
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]