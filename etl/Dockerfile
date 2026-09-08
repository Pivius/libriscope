FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app

RUN useradd -m etluser && chown -R etluser /app
USER etluser

ENV EMBEDDINGS_MODEL=nomic-embed-text

ENTRYPOINT ["./entrypoint.sh"]