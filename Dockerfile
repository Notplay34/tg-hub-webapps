FROM python:3.11-slim

WORKDIR /app

# Системные зависимости (aiosqlite встроен в Python 3.11+)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаём каталог для БД
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# По умолчанию — API; бот переопределяет CMD в compose
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
