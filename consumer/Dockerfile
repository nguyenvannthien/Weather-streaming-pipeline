FROM apache/spark:3.5.0

USER root
# chuyen root de cai dat, cap nhat package manager voi python3 va pip3
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# cai dat uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

#copy cau hinh toml , uv lock
WORKDIR /app
COPY pyproject.toml uv.lock ./

# cai py 3.11 va cai dat cac package trong uv.lock
RUN uv python install 3.11
RUN uv sync --frozen --no-dev --group consumer

#copy consumer vao container
COPY consumer/main.py ./consumer/

# cau hinh moi truong cho spark
ENV JAVA_HOME=/opt/java/openjdk
ENV PYSPARK_PYTHON=/app/.venv/bin/python
ENV PYTHONPATH="/app/.venv/lib/python3.11/site-packages:$PYTHONPATH"

# lenh chay consumer
CMD ["uv", "run", "python", "consumer/main.py"]