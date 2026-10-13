FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --group dashboard

COPY dashboard/app.py ./dashboard/

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]