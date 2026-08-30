FROM node:22-alpine AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install --no-cache-dir ".[dev]"

COPY . .
COPY --from=frontend /frontend/dist ./frontend/dist

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
