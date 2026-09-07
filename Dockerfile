# ——— base image: Python 3.12 + uv ———
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /bot

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv venv .venv && uv sync --frozen --no-dev

COPY . /bot

# Persistent state (credentials, schedule) — mount a volume at /data
RUN mkdir -p /data && chown nobody:nogroup /data

USER nobody
ENV PYTHONUNBUFFERED=1 \
    STATE_PATH=/data/state.json \
    PATH="/bot/.venv/bin:$PATH"

CMD ["python", "/bot/main.py"]
