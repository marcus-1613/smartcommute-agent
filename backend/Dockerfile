# SmartCommute AI 后端镜像
FROM python:3.11-slim

WORKDIR /app

# 安装依赖（分层缓存）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 复制代码
COPY backend/ /app/backend/
COPY mcp_servers/ /app/mcp_servers/

# 设置工作目录与 Python 路径
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    SMARTCOMMUTE_PYTHON=/usr/local/bin/python

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
