# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN --mount=type=cache,target=/root/.cache/pip pip install .
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
