FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --group forecasting

COPY forecasting ./forecasting

RUN mkdir -p /app/models

CMD ["uv", "run", "python", "-m", "forecasting.main"]
