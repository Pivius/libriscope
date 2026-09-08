FROM python:3.11-slim
RUN apt-get update && apt-get install -y build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip && pip install -r etl/requirements.txt pytest
ENV PYTHONPATH=/app
CMD ["pytest","-q"]