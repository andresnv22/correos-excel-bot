FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY muestras ./muestras

CMD ["uv", "run", "--no-sync", "python", "-m", "app.main", "--eml-dir", "muestras", "--out", "salida/facturas"]
