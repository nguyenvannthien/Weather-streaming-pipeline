FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --group historical

COPY historical_loader/main.py ./historical_loader/

CMD ["uv", "run", "python", "historical_loader/main.py"]
