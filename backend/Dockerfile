# Fallback host (Google Cloud Run, Fly, any container platform). Same app as the Vercel deployment:
#   docker build -t axiom-api backend && docker run -p 8000:8000 --env-file backend/.env axiom-api
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOST=0.0.0.0 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY axiom ./axiom
# A container is a long-lived process, so APScheduler can run the briefing itself (SCHEDULER_ENABLED=true).
# Cloud Run sets PORT; proxy headers are honoured whenever PORT is set (see axiom/api/__main__.py).
CMD ["python", "-m", "axiom.api"]
