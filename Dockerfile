# ——— base image: Python 3.12 + uv ———
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /bot

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv venv .venv && uv sync --frozen --no-dev

COPY . /bot

COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/wait_for_selenium.py /wait_for_selenium.py
RUN chmod +x /entrypoint.sh

USER nobody
ENV PYTHONUNBUFFERED=1 \
    PATH="/bot/.venv/bin:$PATH"

ENTRYPOINT ["/entrypoint.sh"]
