FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY resonant_ouroboros ./resonant_ouroboros
COPY tests ./tests
COPY agi_kennis.txt /workspace/agi_kennis.txt

RUN mkdir -p /workspace/data/screenshots /workspace/data/chromadb

RUN chmod +x /workspace/resonant_ouroboros/*.py || true

EXPOSE 7860 8000

CMD ["python", "-m", "resonant_ouroboros.main", "dashboard"]
