FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY agent ./agent
COPY api ./api
COPY core ./core
COPY db ./db
COPY ingestion ./ingestion
COPY jobs ./jobs
RUN pip install --no-cache-dir ".[dev]"

COPY . .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
