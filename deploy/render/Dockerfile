# The always-on Axiom Autopilot API on a free Render web service (render.yaml at the repo root builds this with the
# repo as context). Paper only. The cockpit stays on Vercel and calls this service for /api/trader/*.
# Secrets (Alpaca paper keys, LLM keys, AXIOM_API_TOKEN, HF_TOKEN) are Render environment variables.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOST=0.0.0.0 \
    CACHE_DB=/app/.cache/axiom.db \
    CORS_ORIGINS=https://axiom-ten-henna.vercel.app \
    TRADER_ENABLED=true TRADER_BROKER=alpaca TRADER_BRAIN=desk TRADER_SYMBOLS=BTC/USD,ETH/USD \
    TRADER_AUTONOMY_START=SUPERVISED TRADER_GUEST_ACTIONS=true LLM_CHAIN=nebius,groq,openrouter \
    DB_REPO=amaltomajith/axiom-autopilot-db

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt huggingface_hub==1.23.0
COPY backend/axiom ./axiom
COPY deploy/render/dbsync.py deploy/render/start.sh ./
RUN mkdir -p /app/.cache

# Render sets PORT; axiom.api honours it and the proxy headers.
CMD ["sh", "/app/start.sh"]
