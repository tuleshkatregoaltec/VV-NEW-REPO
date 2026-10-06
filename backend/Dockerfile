FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /uvx /bin/

COPY backend /app/backend

ENV UV_NO_DEV=1

WORKDIR /app/backend
RUN uv sync --locked && apt-get update && apt-get install curl -y

CMD ["uv", "run", "gunicorn", "app.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
