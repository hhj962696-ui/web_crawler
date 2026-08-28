# Synology DS423（ARM64 / Realtek RTD1619B）適用
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Taipei \
    DATA_DIR=/app/data \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    CHROMIUM_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    CHROME_HEADLESS=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-noto-cjk \
    fonts-liberation \
    ca-certificates \
    tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Taipei /etc/localtime \
    && echo "Asia/Taipei" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 映像檔內仍保有一份基礎代碼
COPY . .

RUN mkdir -p /app/data/logs \
    && chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/stats', timeout=5)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]