FROM python:3.11-slim

# 最小系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 项目文件
COPY . .

# 音频目录
RUN mkdir -p /app/audio /app/static

EXPOSE 8765

CMD ["python", "main.py"]