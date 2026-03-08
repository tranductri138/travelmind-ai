FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen --no-install-project

COPY src/ src/
RUN uv sync --no-dev --frozen --no-editable

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

RUN playwright install-deps chromium 

COPY --from=builder /app/src /app/src

EXPOSE 8000

CMD ["uvicorn", "travelmind_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]
